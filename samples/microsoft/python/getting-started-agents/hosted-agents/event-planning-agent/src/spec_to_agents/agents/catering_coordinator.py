# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from agent_framework import BaseChatClient, ChatAgent, ToolProtocol
from dependency_injector.wiring import Provide, inject

from spec_to_agents.models.messages import SpecialistOutput
from spec_to_agents.prompts import catering_coordinator
from spec_to_agents.tools import web_search


@inject
def create_agent(
    client: BaseChatClient = Provide["client"],
    global_tools: dict[str, ToolProtocol] = Provide["global_tools"],
    model_config: dict[str, Any] = Provide["model_config"],
) -> ChatAgent:
    """
    Create Catering Coordinator agent for event planning workflow.

    IMPORTANT: This function uses dependency injection. ALL parameters are
    automatically injected via the DI container. DO NOT pass any arguments
    when calling this function.

    Usage
    -----
    After container is wired:
        agent = catering_coordinator.create_agent()  # No arguments - DI handles it!

    Parameters
    ----------
    client : BaseChatClient
        Automatically injected via Provide["client"]
    global_tools : dict[str, ToolProtocol]
        Automatically injected via Provide["global_tools"]. Dictionary of shared tools available to all agents.

    Returns
    -------
    ChatAgent
        Configured catering coordinator agent with web search capabilities

    Notes
    -----
    Uses custom web_search @ai_function instead of HostedWebSearchTool for
    better control over response formatting for language models.
    """
    # Initialize agent-specific tools
    agent_tools: list[ToolProtocol] = [web_search]

    if global_tools.get("sequential-thinking"):
        # Include MCP sequential-thinking tool from global tools
        agent_tools.append(global_tools["sequential-thinking"])

    return client.create_agent(
        name="catering_coordinator",
        description="Expert in catering services, menu planning, and vendor coordination for events.",
        instructions=catering_coordinator.SYSTEM_PROMPT,
        tools=agent_tools,
        response_format=SpecialistOutput,
        **model_config,
    )
