# Copyright (c) Microsoft. All rights reserved.

"""Model-backed workflow with durable recovery of a pending function call."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agent_framework import (
    Agent,
    AgentResponse,
    AgentSession,
    Content,
    Executor,
    FunctionTool,
    Message,
    WorkflowBuilder,
    WorkflowCheckpointException,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resilient-workflow")

SMOKE_MARKER = "[RESILIENT-WORKFLOW-OK-731]"
SIMULATE_CRASH_TOOL_NAME = "simulate_crash"

WORKFLOW_ID = "resilient-workflow"
MODEL_EXECUTOR_ID = "crash-recovery-agent-executor"
CRASH_EXECUTOR_ID = "simulate-crash-tool"
MODEL_AGENT_ID = "crash-recovery-agent"
MODEL_AGENT_NAME = "Crash Recovery Agent"

CRASH_DELAY_SECONDS = 5
CRASH_EXIT_CODE = 70


class CrashToolExecutor(Executor):
    """Terminate once, then return the pending result after restoration."""

    def __init__(self) -> None:
        super().__init__(id=CRASH_EXECUTOR_ID)
        self._armed_call_id: str | None = None
        self._restored_call_id: str | None = None

    def arm(self, call_id: str) -> None:
        if not call_id:
            raise ValueError("call_id must be a non-empty string")

        if self._armed_call_id is not None and self._armed_call_id != call_id:
            raise RuntimeError(
                "Crash executor is already armed for another function call: "
                f"{self._armed_call_id}"
            )

        self._armed_call_id = call_id

    @handler
    async def handle_function_call(
        self,
        function_call: Content,
        ctx: WorkflowContext[Content],
    ) -> None:
        if function_call.type != "function_call":
            raise TypeError(
                "CrashToolExecutor expected function_call content, "
                f"received {function_call.type!r}"
            )

        if function_call.name != SIMULATE_CRASH_TOOL_NAME:
            raise ValueError(
                f"Unexpected function call {function_call.name!r}; "
                f"expected {SIMULATE_CRASH_TOOL_NAME!r}"
            )

        call_id = function_call.call_id
        if not call_id:
            raise ValueError("simulate_crash function call has no call_id")

        if self._armed_call_id != call_id:
            raise RuntimeError(
                "Crash executor received a call that was not armed at the "
                f"previous checkpoint: received={call_id!r}, "
                f"armed={self._armed_call_id!r}"
            )

        if self._restored_call_id != call_id:
            # This handler runs in the superstep after the pending call was
            # checkpointed. The delay lets Agent Server pair that checkpoint
            # with the stored response before the process terminates.
            logger.warning(
                "Simulating process crash for function call %s in %s seconds.",
                call_id,
                CRASH_DELAY_SECONDS,
            )
            await asyncio.sleep(CRASH_DELAY_SECONDS)
            logging.shutdown()
            os._exit(CRASH_EXIT_CODE)

        # Consume the restore signal so a later, unrelated crash request must
        # cross a fresh checkpoint and terminate once again.
        self._armed_call_id = None
        self._restored_call_id = None

        function_result = Content.from_function_result(
            call_id=call_id,
            result=(
                "Crash recovery succeeded. The hosted process was replaced and "
                "the workflow resumed the pending simulate_crash function call "
                "from its durable checkpoint."
            ),
        )
        await ctx.send_message(function_result)

    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"armed_call_id": self._armed_call_id}

    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        armed_call_id = state.get("armed_call_id")
        if armed_call_id is not None and not isinstance(armed_call_id, str):
            raise WorkflowCheckpointException(
                "CrashToolExecutor checkpoint field 'armed_call_id' must be "
                "a string or null."
            )

        self._armed_call_id = armed_call_id
        self._restored_call_id = armed_call_id
        if armed_call_id:
            logger.info("Restored pending crash function call %s.", armed_call_id)


class CrashRecoveryAgentExecutor(Executor):
    """Run the model and route its declaration-only function call."""

    def __init__(
        self,
        agent: Agent,
        crash_executor: CrashToolExecutor,
    ) -> None:
        super().__init__(id=MODEL_EXECUTOR_ID)
        self._agent = agent
        self._crash_executor = crash_executor
        self._session: AgentSession = agent.create_session()
        self._pending_call: Content | None = None

    @handler
    async def handle_user_messages(
        self,
        messages: list[Message],
        ctx: WorkflowContext[Content, AgentResponse | str],
    ) -> None:
        if self._pending_call is not None:
            raise RuntimeError(
                "Cannot start a new user turn while a function call is pending."
            )

        input_text = "\n".join(message.text for message in messages if message.text)

        # The cloud contract uses a model-free path so routine CI never
        # terminates the process or consumes a long-running model turn.
        if SMOKE_MARKER in input_text:
            await ctx.yield_output(SMOKE_MARKER)
            return

        response = await self._agent.run(
            messages,
            stream=False,
            session=self._session,
        )
        await self._route_agent_response(response, ctx)

    @handler
    async def handle_function_result(
        self,
        function_result: Content,
        ctx: WorkflowContext[Content, AgentResponse | str],
    ) -> None:
        if function_result.type != "function_result":
            raise TypeError(
                "CrashRecoveryAgentExecutor expected function_result content, "
                f"received {function_result.type!r}"
            )

        pending_call = self._pending_call
        if pending_call is None:
            raise RuntimeError(
                "Received a function result without a pending function call."
            )

        if not pending_call.call_id:
            raise RuntimeError("Persisted pending function call has no call_id")

        if function_result.call_id != pending_call.call_id:
            raise RuntimeError(
                "Function result call_id does not match the pending call: "
                f"result={function_result.call_id!r}, "
                f"pending={pending_call.call_id!r}"
            )

        # Declaration-only tool continuation requires a tool-role message with
        # the original call ID. A new user message would start a different turn.
        tool_message = Message(
            role="tool",
            contents=[function_result],
        )

        response = await self._agent.run(
            tool_message,
            stream=False,
            session=self._session,
        )

        if response.user_input_requests:
            requested_names = [request.name for request in response.user_input_requests]
            raise RuntimeError(
                "The recovered model turn requested another unresolved tool "
                f"instead of completing: {requested_names}"
            )

        self._pending_call = None
        await ctx.yield_output(response)

    async def _route_agent_response(
        self,
        response: AgentResponse,
        ctx: WorkflowContext[Content, AgentResponse | str],
    ) -> None:
        requests = response.user_input_requests
        if not requests:
            await ctx.yield_output(response)
            return

        if len(requests) != 1:
            raise RuntimeError(
                "The resilience sample requires exactly one declaration-only "
                f"function call; received {len(requests)}."
            )

        function_call = requests[0]
        if function_call.type != "function_call":
            raise TypeError(
                "Expected a declaration-only function_call request, "
                f"received {function_call.type!r}"
            )

        if function_call.name != SIMULATE_CRASH_TOOL_NAME:
            raise ValueError(f"Unexpected declaration-only tool {function_call.name!r}")

        if not function_call.call_id:
            raise ValueError("simulate_crash function call has no call_id")

        self._pending_call = function_call

        # Arm the target before this superstep completes so its checkpoint
        # identifies the exact function call that recovery may redeliver.
        self._crash_executor.arm(function_call.call_id)
        await ctx.send_message(function_call)

    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {
            "agent_session": self._session.to_dict(),
            "pending_call": (
                self._pending_call.to_dict() if self._pending_call is not None else None
            ),
        }

    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        session_payload = state.get("agent_session")
        if not isinstance(session_payload, dict):
            raise WorkflowCheckpointException(
                "CrashRecoveryAgentExecutor checkpoint field 'agent_session' "
                "must be a dictionary."
            )

        try:
            self._session = AgentSession.from_dict(session_payload)
        except Exception as exc:
            raise WorkflowCheckpointException(
                "Unable to restore the model AgentSession."
            ) from exc

        pending_call_payload = state.get("pending_call")
        if pending_call_payload is None:
            self._pending_call = None
        elif isinstance(pending_call_payload, dict):
            try:
                pending_call = Content.from_dict(pending_call_payload)
            except Exception as exc:
                raise WorkflowCheckpointException(
                    "Unable to restore the pending function call."
                ) from exc

            if pending_call.type != "function_call":
                raise WorkflowCheckpointException(
                    "Restored 'pending_call' is not function_call content."
                )

            self._pending_call = pending_call
        else:
            raise WorkflowCheckpointException(
                "CrashRecoveryAgentExecutor checkpoint field 'pending_call' "
                "must be a dictionary or null."
            )


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    simulate_crash = FunctionTool(
        name=SIMULATE_CRASH_TOOL_NAME,
        description=(
            "Terminate the current hosted-agent process to demonstrate durable "
            "workflow recovery. Call this tool exactly once and only when the "
            "user explicitly requests a crash-recovery demonstration."
        ),
        func=None,
        input_model={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )

    model_agent = Agent(
        client=client,
        id=MODEL_AGENT_ID,
        name=MODEL_AGENT_NAME,
        description=(
            "A model-backed agent that demonstrates workflow recovery after "
            "an intentional process crash."
        ),
        instructions=(
            "You are a crash-recovery demonstration agent. "
            "Call simulate_crash exactly once only when the user explicitly "
            "asks you to demonstrate crash recovery. After the tool result is "
            "returned, briefly explain that the hosted process was replaced "
            "and the workflow resumed the pending tool call from its durable "
            "checkpoint. Preserve any requested canary exactly. For every "
            "other request, answer normally without calling simulate_crash."
        ),
        tools=[simulate_crash],
        default_options={"store": False},
    )

    crash_executor = CrashToolExecutor()
    model_executor = CrashRecoveryAgentExecutor(
        agent=model_agent,
        crash_executor=crash_executor,
    )

    workflow_agent = (
        WorkflowBuilder(
            name=WORKFLOW_ID,
            description=(
                "A model-backed workflow that resumes a pending function call "
                "after hosted process replacement."
            ),
            start_executor=model_executor,
            output_from=[model_executor],
        )
        .add_edge(model_executor, crash_executor)
        .add_edge(crash_executor, model_executor)
        .build()
        .as_agent(
            id=WORKFLOW_ID,
            name=WORKFLOW_ID,
            description=(
                "A resilient model-backed workflow with durable crash recovery."
            ),
        )
    )

    server = ResponsesHostServer(
        workflow_agent,
        options=ResponsesServerOptions(resilient_background=True),
    )
    server.run()


if __name__ == "__main__":
    main()
