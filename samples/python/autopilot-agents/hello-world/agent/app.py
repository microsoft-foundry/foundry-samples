"""Hello World Teams agent.

A minimal digital worker agent: it listens for Teams messages on
``/activity/messages``, feeds each message to an Azure OpenAI model, and replies
with the model's response.
"""

from __future__ import annotations

import logging
import os
from functools import partial

from aiohttp import ClientError
from azure.ai.agentserver.activity import ActivityAgentServerHost
from azure.ai.agentserver.core import configure_observability
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
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
        project = AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        if context.activity.text:
            response = await project.get_openai_client().responses.create(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                input=context.activity.text,
            )
            await send_reply(context, response.output_text)

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
        # The pinned distro otherwise loads the unused OpenAI Agents SDK.
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
