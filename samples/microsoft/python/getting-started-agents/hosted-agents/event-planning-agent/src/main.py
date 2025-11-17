# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
from typing import List

from agent_framework import ChatMessage, WorkflowBuilder, WorkflowContext, WorkflowExecutor, executor
from azure.ai.agentserver.agentframework import from_agent_framework
from dotenv import load_dotenv


def main() -> None:
    from spec_to_agents.container import AppContainer
    from spec_to_agents.workflow.core import build_event_planning_workflow

    load_dotenv()

    container = AppContainer()
    container.wire(modules=[__name__])

    # entrypoint = workflow_entrypoint
    # event_planning_executor = WorkflowExecutor(build_event_planning_workflow(), "event_planning_executor")
    #
    # workflow = (
    #     WorkflowBuilder(
    #         name="Event Planning Workflow",
    #         description=(
    #             "Multi-agent event planning workflow with venue selection, budgeting, "
    #             "catering, and logistics coordination. Supports human-in-the-loop for "
    #             "clarification and approval."
    #         ),
    #         max_iterations=30,  # Prevent infinite loops
    #     )
    #     .set_start_executor(entrypoint)
    #     .add_edge(entrypoint, event_planning_executor)
    #     .build()
    # )
    agent = build_event_planning_workflow().as_agent("event_planning_agent")

    from_agent_framework(agent).run()


@executor(id="workflow_entrypoint")
async def workflow_entrypoint(messages: List[ChatMessage], ctx: WorkflowContext[str, str]):
    prompt = "\n".join([msg.text for msg in messages])
    await ctx.send_message(prompt, target_id="event_planning_executor")


if __name__ == "__main__":
    main()
