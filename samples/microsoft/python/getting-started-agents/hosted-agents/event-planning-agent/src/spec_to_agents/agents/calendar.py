# Copyright (c) Microsoft. All rights reserved.

import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent


async def create_agent() -> A2AAgent:
    """Demonstrates connecting to and communicating with an A2A-compliant agent."""
    # Get A2A agent host from environment
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    # Initialize A2ACardResolver
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)

        # Get agent card
        agent_card = await resolver.get_agent_card(relative_card_path="/.well-known/agent.json")

        # Create A2A agent instance
        return A2AAgent(
            name=agent_card.name,
            description=agent_card.description,
            agent_card=agent_card,
            url=a2a_agent_host,
        )
