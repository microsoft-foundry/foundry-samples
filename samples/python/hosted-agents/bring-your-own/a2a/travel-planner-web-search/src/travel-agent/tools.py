# Copyright (c) Microsoft. All rights reserved.
"""Card-derived Copilot tools with request-scoped native A2A delegation."""

import json
import logging
from time import perf_counter

from a2a.client import Client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest, TaskState
from copilot import Tool, ToolInvocation, ToolResult
from opentelemetry import context, trace

logger = logging.getLogger("a2a.travel.tools")


def build_tools(
    agents: list[tuple[AgentCard, Client]],
    calls: list[dict[str, str]],
    failures: list[str],
) -> list[Tool]:
    request_context = context.get_current()
    request_span = trace.get_current_span(request_context).get_span_context()

    def tool(name: str, card: AgentCard, client: Client) -> Tool:
        async def handler(invocation: ToolInvocation) -> ToolResult:
            started = perf_counter()
            try:
                arguments = invocation.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict) or set(arguments) != {"message"}:
                    raise ValueError("Supply exactly one specialist message")
                message = arguments["message"]
                if isinstance(message, dict):
                    message = json.dumps(message)
                if not isinstance(message, str) or not message.strip():
                    raise ValueError(
                        "Specialist message must be nonempty text or a JSON object"
                    )
                parent_context = context.get_current()
                callback_span = trace.get_current_span(
                    parent_context
                ).get_span_context()
                if request_span.is_valid and (
                    not callback_span.is_valid
                    or callback_span.trace_id != request_span.trace_id
                ):
                    parent_context = request_context
                    logger.warning(
                        "A2A_CALLBACK_CONTEXT_RESTORED agent=%s tool=%s tool_call_id=%s "
                        "reason=%s request_trace=%032x callback_trace=%032x",
                        card.name,
                        name,
                        invocation.tool_call_id,
                        "missing_context"
                        if not callback_span.is_valid
                        else "different_trace",
                        request_span.trace_id,
                        callback_span.trace_id,
                    )
                # Restore context across the runtime callback without adding a custom span.
                token = context.attach(parent_context)
                try:
                    active_span = trace.get_current_span().get_span_context()
                    logger.info(
                        "A2A_REQUEST_STARTED agent=%s method=SendMessage tool_call_id=%s "
                        "trace_id=%032x parent_span_id=%016x",
                        card.name,
                        invocation.tool_call_id,
                        active_span.trace_id,
                        active_span.span_id,
                    )
                    tasks = [
                        event.task
                        async for event in client.send_message(
                            SendMessageRequest(
                                message=new_text_message(message, role=Role.ROLE_USER)
                            )
                        )
                        if event.HasField("task")
                    ]
                    if (
                        len(tasks) != 1
                        or tasks[0].status.state != TaskState.TASK_STATE_COMPLETED
                    ):
                        raise RuntimeError(
                            f"{card.name} did not return one completed A2A Task"
                        )
                    task = tasks[0]
                    answer = "\n".join(
                        get_artifact_text(artifact) for artifact in task.artifacts
                    )
                    if not task.id or not answer.strip():
                        raise RuntimeError(
                            f"{card.name} returned no Task ID or answer artifact"
                        )
                    result = {"agent": card.name, "task_id": task.id, "answer": answer}
                    calls.append({"tool": name, **result})
                    logger.info(
                        "A2A_DELEGATION_COMPLETED agent=%s task_id=%s state=COMPLETED "
                        "tool_call_id=%s elapsed_ms=%.1f trace_id=%032x",
                        card.name,
                        task.id,
                        invocation.tool_call_id,
                        (perf_counter() - started) * 1000,
                        active_span.trace_id,
                    )
                    return ToolResult(
                        text_result_for_llm=json.dumps(result),
                        result_type="success",
                    )
                finally:
                    context.detach(token)
            except Exception as error:
                failures.append(name)
                logger.error(
                    "A2A_DELEGATION_FAILED agent=%s method=SendMessage tool_call_id=%s "
                    "error_type=%s elapsed_ms=%.1f trace_id=%032x",
                    card.name,
                    invocation.tool_call_id,
                    type(error).__name__,
                    (perf_counter() - started) * 1000,
                    request_span.trace_id,
                )
                raise

        return Tool(
            name=name,
            description=json.dumps(
                {
                    "agent": card.name,
                    "description": card.description,
                    "skills": [
                        {"name": skill.name, "description": skill.description}
                        for skill in card.skills
                    ],
                }
            ),
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "message": {
                        "type": ["string", "object"],
                        "description": "Self-contained request in the format advertised by this agent's skills.",
                    }
                },
                "required": ["message"],
            },
            handler=handler,
        )

    return [
        tool(f"consult_agent_{index + 1}", card, client)
        for index, (card, client) in enumerate(agents)
    ]
