"""Deep research agent assembly."""

from datetime import datetime
from typing import Any

from deepagents import SubAgent, create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from research_agent.prompts import (
    REPORT_PUBLICATION_INSTRUCTIONS,
    REPORT_PUBLICATION_STEP,
    RESEARCH_WORKFLOW_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    SUBAGENT_DELEGATION_INSTRUCTIONS,
)

MAX_CONCURRENT_RESEARCH_UNITS = 3
MAX_RESEARCHER_ITERATIONS = 3


def build_agent(
    model: ChatOpenAI,
    checkpointer: BaseCheckpointSaver[Any],
    tools: list[BaseTool],
    report_export_tool: BaseTool | None = None,
):
    """Build the coordinator and its focused research subagent."""
    current_date = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    instructions = (
        RESEARCH_WORKFLOW_INSTRUCTIONS.format(
            report_publication_step=(
                REPORT_PUBLICATION_STEP if report_export_tool is not None else ""
            ),
            report_publication_instructions=(
                REPORT_PUBLICATION_INSTRUCTIONS
                if report_export_tool is not None
                else ""
            ),
        )
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
            max_concurrent_research_units=MAX_CONCURRENT_RESEARCH_UNITS,
            max_researcher_iterations=MAX_RESEARCHER_ITERATIONS,
        )
    )
    research_sub_agent: SubAgent = {
        "name": "research-agent",
        "description": "Delegate research to the sub-agent. Give one topic at a time.",
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": tools,
    }

    return create_deep_agent(
        model=model,
        tools=tools + [report_export_tool] if report_export_tool is not None else tools,
        system_prompt=instructions,
        subagents=[research_sub_agent],
        middleware=[TodoListMiddleware()],
        checkpointer=checkpointer,
        name="foundry-deep-research-agent",
    )
