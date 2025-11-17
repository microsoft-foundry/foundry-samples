# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from agent_framework import BaseChatClient, ChatAgent, ToolProtocol
from dependency_injector.wiring import Provide, inject

from spec_to_agents.prompts import event_coordinator


@inject
def create_agent(
    client: BaseChatClient = Provide["client"],
    global_tools: dict[str, ToolProtocol] = Provide["global_tools"],
    model_config: dict[str, Any] = Provide["model_config"],
) -> ChatAgent:
    """
    Create Event Coordinator agent for workflow orchestration.

    Parameters
    ----------
    client : AzureAIAgentClient
        AI client for agent creation

    Returns
    -------
    ChatAgent
        Configured event coordinator agent for workflow orchestration
    """
    agent_tools: list[ToolProtocol] = []

    if global_tools.get("sequential-thinking"):
        # Include MCP sequential-thinking tool from global tools
        agent_tools.append(global_tools["sequential-thinking"])
    return client.create_agent(
        name="event_coordinator",
        instructions=event_coordinator.SYSTEM_PROMPT,
        tools=agent_tools,
        **model_config,
    )
