# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from agent_framework import BaseChatClient, ChatAgent, ToolProtocol
from dependency_injector.wiring import Provide, inject

from spec_to_agents.models.messages import SpecialistOutput
from spec_to_agents.prompts import logistics_manager
from spec_to_agents.tools import (
    create_calendar_event,
    delete_calendar_event,
    get_weather_forecast,
    list_calendar_events,
)


@inject
def create_agent(
    client: BaseChatClient = Provide["client"],
    global_tools: dict[str, ToolProtocol] = Provide["global_tools"],
    model_config: dict[str, Any] = Provide["model_config"],
) -> ChatAgent:
    """
    Create Logistics Manager agent for event planning workflow.

    IMPORTANT: This function uses dependency injection. ALL parameters are
    automatically injected via the DI container. DO NOT pass any arguments
    when calling this function.

    Usage
    -----
    After container is wired:
        agent = logistics_manager.create_agent()  # No arguments - DI handles it!

    Parameters
    ----------
    client : BaseChatClient
        Automatically injected via Provide["client"]
    global_tools : dict[str, ToolProtocol]
        Automatically injected via Provide["global_tools"]

    Returns
    -------
    ChatAgent
        Configured logistics manager agent with weather and calendar capabilities
    """
    # Initialize agent-specific tools
    agent_tools: list[ToolProtocol] = [
        get_weather_forecast,
        create_calendar_event,
        list_calendar_events,
        delete_calendar_event,
    ]

    if global_tools.get("sequential-thinking"):
        # Include MCP sequential-thinking tool from global tools
        agent_tools.append(global_tools["sequential-thinking"])

    return client.create_agent(
        name="logistics_manager",
        description="Expert in event logistics, scheduling, and weather planning.",
        instructions=logistics_manager.SYSTEM_PROMPT,
        tools=agent_tools,
        response_format=SpecialistOutput,
        **model_config,
    )
