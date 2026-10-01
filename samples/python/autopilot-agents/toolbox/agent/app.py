"""Microsoft 365 Autopilot that uses tools from a Foundry Toolbox."""

from __future__ import annotations

import logging
import os
from functools import lru_cache, partial

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox
from aiohttp import ClientError
from azure.ai.agentserver.activity import ActivityAgentServerHost
from azure.ai.agentserver.core import configure_observability
from azure.identity import DefaultAzureCredential
from microsoft_agents.hosting.core import (
    AgentApplication,
    RouteRank,
    TurnContext,
    TurnState,
)

from .activity_routing import (
    selector,
    teams_direct_message,
    teams_group_chat_message,
    teams_tagged_channel_message,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = """You are a concise assistant in Microsoft Teams.
Use the tools from your Foundry Toolbox whenever they can provide a more accurate
answer. Use web search for current information, code interpreter for calculations
or data analysis, and api_specs tools for questions about Azure REST APIs. Briefly
identify the tool-backed evidence you used in the answer."""


@lru_cache(maxsize=1)
def get_model_runtime() -> tuple[DefaultAzureCredential, FoundryChatClient]:
    """Create the process-scoped credential and model client."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    return credential, client


def create_tool_agent() -> Agent:
    """Create a request-scoped agent and toolbox connection."""
    credential, client = get_model_runtime()
    toolbox = FoundryToolbox(credential)
    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=toolbox,
        default_options={"store": False},
    )


def register_handlers(agent: AgentApplication[TurnState]) -> None:
    """Register the supported Teams surfaces on the host's agent application."""

    async def send_reply(context: TurnContext, text: str) -> None:
        try:
            await context.send_activity(text)
        except (ClientError, TimeoutError):
            logger.exception("Failed to send reply")

    @agent.error
    async def on_error(context: TurnContext, error: Exception) -> None:
        logger.error("Unhandled turn error", exc_info=error)
        await send_reply(context, "Sorry, something went wrong handling your message.")

    async def respond(context: TurnContext, surface: str) -> None:
        logger.info(
            "Received %s: %r",
            surface,
            context.activity.text,
            extra={"surface": surface},
        )
        if not context.activity.text:
            return

        async with create_tool_agent() as tool_agent:
            response = await tool_agent.run(context.activity.text)

        await send_reply(context, response.text)

    async def on_teams_direct_message(
        context: TurnContext, _state: TurnState
    ) -> None:
        await respond(context, "Teams direct message")

    async def on_teams_group_chat(
        context: TurnContext, _state: TurnState
    ) -> None:
        await respond(context, "Teams group chat message")

    async def on_teams_tagged_channel_message(
        context: TurnContext, _state: TurnState
    ) -> None:
        await respond(context, "Teams tagged channel message")

    async def on_unhandled(context: TurnContext, _state: TurnState) -> None:
        logger.info(
            "Ignoring unsupported activity type=%r channel=%r",
            context.activity.type,
            context.activity.channel_id,
        )

    agent.add_route(selector(teams_direct_message), on_teams_direct_message)
    agent.add_route(selector(teams_group_chat_message), on_teams_group_chat)
    agent.add_route(
        selector(teams_tagged_channel_message),
        on_teams_tagged_channel_message,
    )
    agent.add_route(
        lambda _context: True,
        on_unhandled,
        rank=RouteRank.LAST,
    )


def build_app() -> ActivityAgentServerHost:
    """Build the Foundry host and register Teams handlers."""
    host = ActivityAgentServerHost(
        digital_worker=True,
        configure_observability=partial(
            configure_observability,
            instrumentation_options={"openai_agents": {"enabled": False}},
        ),
    )
    register_handlers(host.agent_app)
    return host


def main() -> None:
    host = build_app()
    logger.info("Starting agent...")
    host.run()
