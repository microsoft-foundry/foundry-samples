# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from agent_framework import BaseChatClient, ChatAgent, HostedCodeInterpreterTool, ToolProtocol
from dependency_injector.wiring import Provide, inject

from spec_to_agents.models.messages import SpecialistOutput
from spec_to_agents.prompts import budget_analyst


@inject
def create_agent(
    client: BaseChatClient = Provide["client"],
    global_tools: dict[str, ToolProtocol] = Provide["global_tools"],
    model_config: dict[str, Any] = Provide["model_config"],
) -> ChatAgent:
    """
    Create Budget Analyst agent for event planning workflow.

    IMPORTANT: This function uses dependency injection. ALL parameters are
    automatically injected via the DI container. DO NOT pass any arguments
    when calling this function.

    Usage
    -----
    After container is wired:
        agent = budget_analyst.create_agent()  # No arguments - DI handles it!

    Parameters
    ----------
    client : BaseChatClient
        Automatically injected via Provide["client"]
    global_tools : dict[str, ToolProtocol]
        Automatically injected via Provide["global_tools"]
        Dictionary of globally shared tools. Keys:
        - "sequential-thinking": MCP sequential thinking tool

    Returns
    -------
    ChatAgent
        Configured budget analyst agent with code interpreter capabilities

    Notes
    -----
    MCP sequential-thinking tool was removed because it interferes with
    structured output generation. The agent would complete its thinking
    process but fail to return a final structured response, causing
    ValueError in the workflow.
    """
    # Initialize agent-specific tools
    code_interpreter = HostedCodeInterpreterTool(
        description=(
            "Execute Python code for complex financial calculations, budget analysis, "
            "cost projections, and data visualization."
        ),
    )

    # Agent-specific tools only (Budget Analyst doesn't need MCP tool)
    agent_tools: list[ToolProtocol] = [code_interpreter]

    if global_tools.get("sequential-thinking"):
        # Include MCP sequential-thinking tool from global tools
        agent_tools.append(global_tools["sequential-thinking"])

    return client.create_agent(
        name="budget_analyst",
        description="Expert in financial planning, budgeting, and cost analysis for events.",
        instructions=budget_analyst.SYSTEM_PROMPT,
        tools=agent_tools,
        response_format=SpecialistOutput,
        **model_config,
    )
