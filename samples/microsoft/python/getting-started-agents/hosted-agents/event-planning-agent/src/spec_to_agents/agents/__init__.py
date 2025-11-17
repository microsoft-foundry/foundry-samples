# Copyright (c) Microsoft. All rights reserved.
import asyncio

from agent_framework import ChatAgent
from agent_framework.a2a import A2AAgent

from spec_to_agents.agents import (
    budget_analyst,
    calendar,
    catering_coordinator,
    logistics_manager,
    venue_specialist,
)
from spec_to_agents.utils.clients import create_agent_client_for_devui


def export_agents() -> list[ChatAgent | A2AAgent]:
    """
    Export all agents for registration in DevUI.

    Note: Only the workflow is exported. Individual agents are internal
    to the workflow and not meant to be used standalone in DevUI.

    Dependencies are injected via DI container which must be wired before
    calling this function (done in main.py and console.py).

    Returns
    -------
    list[ChatAgent]
        List containing all specialist agents
    """
    # Create agents (dependencies injected automatically via @inject)
    venue_agent = venue_specialist.create_agent()
    budget_agent = budget_analyst.create_agent()
    catering_agent = catering_coordinator.create_agent()
    logistics_agent = logistics_manager.create_agent()

    # Calendar agent is optional - only load if A2A_AGENT_HOST is configured
    agents = [venue_agent, budget_agent, catering_agent, logistics_agent]
    try:
        calendar_agent = asyncio.run(calendar.create_agent())
        agents.append(calendar_agent)
    except ValueError as e:
        if "A2A_AGENT_HOST" in str(e):
            # Calendar agent not configured, skip it
            pass
        else:
            raise

    return agents


__all__ = ["create_agent_client_for_devui", "export_agents"]
