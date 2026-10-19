"""Host a toolbox-backed Autopilot on the Foundry Activity protocol."""

import logging
from functools import partial

from aiohttp import ClientError
from azure.ai.agentserver.activity import ActivityAgentServerHost
from azure.ai.agentserver.core import configure_observability
from microsoft_agents.hosting.core import (
    AgentApplication,
    RouteRank,  # pyright: ignore[reportPrivateImportUsage]
    TurnContext,
    TurnState,
)

from .activity_routing import (
    selector,
    teams_direct_message,
    teams_group_chat_message,
    teams_tagged_channel_message,
)
from .toolbox import Settings, answer

logger = logging.getLogger(__name__)


def register_handlers(agent: AgentApplication[TurnState], settings: Settings) -> None:
    async def send_reply(context: TurnContext, text: str) -> None:
        try:
            await context.send_activity(text)
        except (ClientError, TimeoutError):
            logger.exception("Failed to send Teams reply")

    @agent.error
    async def on_error(context: TurnContext, error: Exception) -> None:
        logger.error("Failed to answer using the Foundry Toolbox", exc_info=error)
        await send_reply(
            context,
            "Sorry, I couldn't answer using the Foundry Toolbox. "
            "Please try again; if this continues, ask the agent owner to check "
            "the toolbox configuration and permissions.",
        )

    async def respond(context: TurnContext, _state: TurnState) -> None:
        message = (TurnContext.remove_recipient_mention(context.activity) or "").strip()
        if not message:
            await send_reply(
                context,
                "Ask me about Microsoft documentation or current public web information.",
            )
            return
        logger.info("Answering a Teams message with the Foundry Toolbox")
        await send_reply(context, await answer(settings, message))

    for matcher in (
        teams_direct_message,
        teams_group_chat_message,
        teams_tagged_channel_message,
    ):
        agent.add_route(selector(matcher), respond)

    async def on_unhandled(context: TurnContext, _state: TurnState) -> None:
        logger.info("Ignoring unsupported activity type=%s", context.activity.type)

    agent.add_route(lambda _context: True, on_unhandled, rank=RouteRank.LAST)


def build_app() -> ActivityAgentServerHost:
    settings = Settings.from_env()
    host = ActivityAgentServerHost(
        digital_worker=True,
        configure_observability=partial(
            configure_observability,
            instrumentation_options={"openai_agents": {"enabled": False}},
        ),
    )
    register_handlers(host.agent_app, settings)
    return host


def main() -> None:
    host = build_app()
    logger.info("Starting Foundry Toolbox Autopilot")
    host.run()
