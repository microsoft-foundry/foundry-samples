"""Activity hosting for meeting membership, start, end, and artifact availability."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import partial

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from azure.ai.agentserver.activity import ActivityAgentServerHost
from azure.ai.agentserver.core import configure_observability
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from microsoft_agents.activity import Activity
from microsoft_agents.activity.teams import TeamsChannelData
from microsoft_agents.hosting.core import AgentApplication, RouteRank, TurnContext, TurnState
from microsoft_agents.hosting.msteams import TeamsAgentExtension, TeamsTurnContext
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue
from microsoft_teams.api.models import ChannelData
from openai import AsyncOpenAI
from pydantic import ValidationError

from .workiq import (
    WORKIQ_ENDPOINT, WORKIQ_SCOPE, MeetingWorkIQ, WorkIQError, WorkIQTransportDiagnostics,
)
from .hosting import MeetingActivityHost
from .meeting_analysis import MeetingAnalysis
from .meeting_lifecycle import (
    MeetingLifecycle, MeetingState, RecordingAvailable, utc_time,
)
from .request_logging import ActivityPayloadLoggingMiddleware

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    model: str
    log_activity_payloads: bool = False
    log_workiq_payloads: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        log_payloads = os.environ.get("MEETING_LOG_ACTIVITY_PAYLOADS", "false").lower()
        if log_payloads not in {"true", "false"}:
            raise ValueError("MEETING_LOG_ACTIVITY_PAYLOADS must be true or false.")
        log_workiq = os.environ.get("MEETING_LOG_WORKIQ_PAYLOADS", "false").lower()
        if log_workiq not in {"true", "false"}:
            raise ValueError("MEETING_LOG_WORKIQ_PAYLOADS must be true or false.")
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].strip()
        model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"].strip()
        if not endpoint or not model:
            raise ValueError("A Foundry project endpoint and model deployment are required.")
        return cls(
            endpoint, model, log_payloads == "true",
            log_workiq == "true",
        )


def get_meeting_conversation_id(
    activity: Activity, meeting: MeetingStartEventValue | MeetingEndEventValue,
) -> str:
    """Validate the SDK meeting event and return its conversation ID."""
    if any(not value.strip() for value in (
        meeting.id, meeting.title, meeting.meeting_type, meeting.join_url,
    )):
        raise ValueError("Meeting event fields must not be empty.")
    if meeting.meeting_type.strip() != "Scheduled":
        raise ValueError("Only scheduled, non-channel meeting events are supported.")
    timestamp = meeting.start_time if isinstance(meeting, MeetingStartEventValue) else meeting.end_time
    utc_time(timestamp.isoformat())
    if not activity.conversation or not activity.conversation.id:
        raise ValueError("Meeting event has no conversation ID.")
    return activity.conversation.id


def is_supported_teams_group_chat(activity: Activity) -> bool:
    conversation = activity.conversation
    agent_tenant = activity.get_agentic_tenant_id()
    channel_data = activity.channel_data or {}
    if isinstance(channel_data, ChannelData):
        channel_tenant_id = channel_data.tenant.id if channel_data.tenant else None
    elif isinstance(channel_data, dict):
        channel_tenant = channel_data.get("tenant", {})
        if not isinstance(channel_tenant, dict):
            return False
        channel_tenant_id = channel_tenant.get("id")
    else:
        return False
    tenant_ids = [
        tenant for tenant in (
            conversation.tenant_id if conversation else None,
            channel_tenant_id,
        )
        if tenant is not None
    ]
    return bool(
        activity.channel_id and activity.channel_id.channel == "msteams"
        and activity.is_agentic_request()
        and activity.get_agentic_user() and activity.get_agentic_instance_id()
        and conversation and conversation.id
        and conversation.conversation_type != "channel"
        and (conversation.conversation_type == "groupChat" or conversation.is_group is True)
        and tenant_ids
        and agent_tenant
        and all(isinstance(tenant, str) and tenant.lower() == agent_tenant.lower() for tenant in tenant_ids)
    )


def is_added_to_meeting(activity: Activity) -> bool:
    if not (
        activity.is_conversation_update()
        and is_supported_teams_group_chat(activity)
        and activity.recipient and activity.recipient.id
        and any(member.id == activity.recipient.id for member in activity.members_added or [])
    ):
        return False
    if isinstance(activity.channel_data, ChannelData):
        channel_data = activity.channel_data
    else:
        if activity.channel_data.get("meeting") is None:
            return False
        try:
            channel_data = TeamsChannelData.model_validate(activity.channel_data)
        except ValidationError:
            logger.warning("Ignoring invalid Teams channel data in a meeting membership update")
            return False
    return bool(channel_data.meeting and channel_data.meeting.id and channel_data.meeting.id.strip())


def is_recording_available(activity: Activity) -> bool:
    return (
        is_supported_teams_group_chat(activity)
        and RecordingAvailable.from_activity(activity) is not None
    )


async def on_error(context: TurnContext, error: Exception) -> None:
    # Exception messages may contain request URLs or meeting content.
    if isinstance(error, ExceptionGroup):
        for nested in error.exceptions:
            await on_error(context, nested)
    elif isinstance(error, ValidationError):
        issues = [
            {"location": item["loc"], "type": item["type"]}
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        ]
        logger.error(
            "Meeting turn failed (%s): activity=%s model=%s issues=%s",
            type(error).__name__, context.activity.name, error.title, json.dumps(issues),
        )
    elif isinstance(error, WorkIQError):
        logger.error(
            "Meeting turn failed (WorkIQError): status=%s code=%s inner_code=%s request_id=%s diagnostics=%s",
            error.status, error.code, error.inner_code, error.request_id,
            json.dumps(error.diagnostic_fields(), sort_keys=True),
        )
    elif isinstance(error, httpx.HTTPStatusError):
        logger.error("Work IQ transport failed: status=%s", error.response.status_code)
    else:
        logger.error("Meeting turn failed (%s)", type(error).__name__)


async def ignore(context: TurnContext, _state: TurnState) -> None:
    logger.debug("Ignoring unsupported activity")


class MeetingHandlers:
    def __init__(self, agent: AgentApplication[TurnState], settings: Settings) -> None:
        self.agent = agent
        self.settings = settings
        self.lifecycle_lock = asyncio.Lock()

    async def on_added_to_meeting(self, context: TurnContext, turn: TurnState) -> None:
        logger.info("Agent added to a meeting chat; waiting for the meeting-start event")
        async with self.workiq_client(context) as workiq:
            title = await workiq.get_chat_title(context.activity.conversation.id)
        await context.send_activity(Activity(
            type="message",
            text=f"Hello, thank you for adding me to {title}!",
            text_format="plain",
        ))

    @asynccontextmanager
    async def workiq_client(self, context: TurnContext) -> AsyncIterator[MeetingWorkIQ]:
        token = await self.agent.auth.exchange_token(
            context, scopes=[WORKIQ_SCOPE], auth_handler_id="AGENTIC"
        )
        agent_user_id = context.activity.get_agentic_user()
        if not token.token or not agent_user_id:
            raise RuntimeError("Agent-user Work IQ authorization returned no token or identity.")
        diagnostics = WorkIQTransportDiagnostics(log_payloads=self.settings.log_workiq_payloads)
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token.token}", "Accept-Encoding": "identity"},
            timeout=30, follow_redirects=False,
            event_hooks={"response": [diagnostics.on_response]},
        ) as client:
            async with streamable_http_client(WORKIQ_ENDPOINT, http_client=client) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                    await session.initialize()
                    yield MeetingWorkIQ(
                        session, transport_diagnostics=diagnostics,
                        log_payloads=self.settings.log_workiq_payloads,
                    )

    @asynccontextmanager
    async def clients(self, context: TurnContext) -> AsyncIterator[tuple[MeetingWorkIQ, AsyncOpenAI]]:
        async with (
            self.workiq_client(context) as workiq,
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=self.settings.project_endpoint, credential=credential) as project,
        ):
            async with project.get_openai_client() as model_client:
                yield workiq, model_client

    @asynccontextmanager
    async def processor(self, context: TurnContext, turn: TurnState) -> AsyncIterator[MeetingLifecycle]:
        activity = context.activity
        if not is_supported_teams_group_chat(activity):
            raise ValueError("Expected a Teams meeting chat with consistent agent-user identity.")
        async with self.lifecycle_lock:
            # Refresh inside the lock so concurrent turns in this process cannot
            # both act on a stale copy. Cross-replica exactly-once delivery is not provided.
            await turn.conversation.load(context, force=True)
            key = (
                f"meeting_lifecycle_v1:{activity.get_agentic_tenant_id().lower()}:"
                f"{activity.get_agentic_user()}:{activity.get_agentic_instance_id()}"
            )
            state = MeetingState.model_validate(turn.conversation.get_value(key, dict))

            async def save() -> None:
                turn.conversation.set_value(key, state.model_dump(mode="json"))
                await turn.conversation.save(context, force=True)

            async with self.clients(context) as (workiq, model_client):
                yield MeetingLifecycle(
                    state, workiq, MeetingAnalysis(model_client, self.settings.model),
                    save, context.send_activity,
                )

    async def on_meeting_start(
        self, context: TeamsTurnContext, turn: TurnState, meeting: MeetingStartEventValue,
    ) -> None:
        logger.info("Meeting-start handler entered")
        chat_id = get_meeting_conversation_id(context.activity, meeting)
        async with self.processor(context, turn) as processor:
            await processor.start(meeting, chat_id)

    async def on_meeting_end(
        self, context: TeamsTurnContext, turn: TurnState, meeting: MeetingEndEventValue,
    ) -> None:
        logger.info("Meeting-end handler entered")
        chat_id = get_meeting_conversation_id(context.activity, meeting)
        async with self.processor(context, turn) as processor:
            await processor.end(meeting, chat_id)

    async def on_recording_available(self, context: TurnContext, turn: TurnState) -> None:
        signal = RecordingAvailable.from_activity(context.activity)
        if signal is None:
            raise ValueError("Expected a transcript availability notification.")
        async with self.processor(context, turn) as processor:
            await processor.recording_available(signal)


def register_handlers(agent: AgentApplication[TurnState], handlers: MeetingHandlers) -> None:
    agent.error(on_error)
    teams = TeamsAgentExtension(agent)
    teams.meetings.start(auth_handlers=["AGENTIC"])(handlers.on_meeting_start)
    teams.meetings.end(auth_handlers=["AGENTIC"])(handlers.on_meeting_end)
    agent.add_route(
        lambda context: is_recording_available(context.activity),
        handlers.on_recording_available,
        auth_handlers=["AGENTIC"],
    )
    agent.add_route(
        lambda context: is_added_to_meeting(context.activity),
        handlers.on_added_to_meeting,
        auth_handlers=["AGENTIC"],
    )
    agent.add_route(lambda _context: True, ignore, rank=RouteRank.LAST)


def build_app() -> ActivityAgentServerHost:
    settings = Settings.from_env()
    host = MeetingActivityHost(
        configure_observability=partial(
            configure_observability,
            instrumentation_options={"openai_agents": {"enabled": False}},
        ),
    )
    if settings.log_activity_payloads:
        host.add_middleware(ActivityPayloadLoggingMiddleware)
        logger.warning("Activity request body logging is enabled. Use synthetic test meetings only.")
    if settings.log_workiq_payloads:
        logger.warning(
            "Unredacted Work IQ payload logging is enabled. Tool arguments, responses, "
            "and errors may contain meeting content or personal data. Use restricted test logs only."
        )
    handlers = MeetingHandlers(host.agent_app, settings)
    register_handlers(host.agent_app, handlers)
    return host


def main() -> None:
    build_app().run()
