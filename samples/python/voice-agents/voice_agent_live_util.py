"""Small shared lifecycle helpers for the direct SDK Native GPT Live samples.

Requires azure-ai-projects[voice]==2.11.0. These helpers never use Realtime
commands or mutate an existing agent. Run one of voice_agent_live_*.py instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
import time
from typing import Any
from uuid import uuid4
from weakref import WeakKeyDictionary

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.aio.operations import AsyncBetaLiveConnection
from azure.core.exceptions import HttpResponseError

SAMPLE_RATE = 24000
FRAME_BYTES = 2400  # 50 ms of mono PCM16LE.
EVENT_TIMEOUT = 30.0
CLOSE_TIMEOUT = 10.0
_PENDING_READS: WeakKeyDictionary[
    AsyncBetaLiveConnection, asyncio.Task[Any]
] = WeakKeyDictionary()


class LiveReceiveTimeout(TimeoutError):
    """The sample's receive deadline expired, not the underlying transport."""


def audio_settings() -> models.LiveInitialSessionAudioParam:
    return models.LiveInitialSessionAudioParam(
        format=models.LiveSessionAudioFormatPCMParam(rate=24000),
        output=models.LiveInitialSessionAudioOutputParam(voice="marin"),
    )


async def delete_owned_version(
    project: AIProjectClient, agent_name: str, agent_version: str
) -> None:
    await project.agents.delete_version(
        agent_name=agent_name, agent_version=agent_version
    )
    try:
        await project.agents.get_version(
            agent_name=agent_name, agent_version=agent_version
        )
    except HttpResponseError as error:
        if error.status_code != 404:
            raise
    else:
        raise RuntimeError("The owned agent version is still readable after deletion.")
    print(f"Confirmed owned agent {agent_name} version {agent_version}: GET 404.")


async def delete_owned_conversation(
    project: AIProjectClient, agent_name: str, conversation_id: str
) -> None:
    conversations = project.beta.voice_agents.live_conversations
    await conversations.delete(agent_name=agent_name, conversation_id=conversation_id)
    try:
        await conversations.get(agent_name=agent_name, conversation_id=conversation_id)
    except HttpResponseError as error:
        if error.status_code != 404:
            raise
    else:
        raise RuntimeError(
            "The owned Live conversation is still readable after deletion."
        )
    print(f"Confirmed owned Live conversation {conversation_id}: GET 404.")


async def create_owned_agent(
    project: AIProjectClient,
    cleanup: AsyncExitStack,
    scenario: str,
    definition: models.AgentDefinition,
) -> models.AgentVersionDetails:
    """Register exact-version cleanup immediately, including subsequent failures."""
    name = f"sample-live-{scenario}-{uuid4().hex[:12]}"
    agent = await project.agents.create_version(agent_name=name, definition=definition)
    cleanup.push_async_callback(delete_owned_version, project, name, agent.version)
    print(f"Created owned agent {name}, version {agent.version}; cleanup registered.")
    return agent


def check_event(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Raise service/backend failures without dumping events, credentials, or audio."""
    if event.get("type") == "error":
        error = event.get("error")
        if not isinstance(error, Mapping):
            raise RuntimeError("Malformed Live error event.")
        raise RuntimeError(
            f"Live error {error.get('code')} "
            f"(parameter {error.get('param')}; "
            f"client event {error.get('client_event_id') or event.get('client_event_id')})"
        )
    if event.get("type") == "transport.failed":
        raise RuntimeError("Live transport failed.")
    if event.get("type") != "response.event":
        return {}
    nested = event.get("event")
    if not isinstance(nested, Mapping) or not isinstance(nested.get("type"), str):
        raise RuntimeError("Malformed Live backend response.event.")
    response = nested.get("response") or {}
    if not isinstance(response, Mapping):
        raise RuntimeError("Malformed Live backend response snapshot.")
    if nested["type"] in (
        "error",
        "response.failed",
        "response.incomplete",
        "response.cancelled",
    ) or response.get("status") in ("failed", "incomplete", "cancelled"):
        raise RuntimeError(
            f"Live backend failed: {nested['type']} (status={response.get('status')})."
        )
    return nested


async def receive(
    connection: AsyncBetaLiveConnection, deadline: float
) -> Mapping[str, Any]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LiveReceiveTimeout("Live receive deadline expired.")
    pending = _PENDING_READS.get(connection)
    if pending is None:
        pending = asyncio.create_task(connection.recv())
        _PENDING_READS[connection] = pending
    done, _ = await asyncio.wait({pending}, timeout=remaining)
    if not done:
        # Cancelling aiohttp receive can mark the socket abnormally closed and lose
        # session.closed. Keep the one pending read for the next lifecycle phase.
        raise LiveReceiveTimeout("Live receive deadline expired.")
    _PENDING_READS.pop(connection, None)
    event = pending.result()
    if not isinstance(event, Mapping):
        raise RuntimeError("Malformed Live server event.")
    check_event(event)
    return event


async def wait_event(
    connection: AsyncBetaLiveConnection,
    event_type: str,
    *,
    timeout: float = EVENT_TIMEOUT,
    client_event_id: str | None = None,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        event = await receive(connection, deadline)
        if event.get("type") == event_type and (
            client_event_id is None or event.get("client_event_id") == client_event_id
        ):
            return event
        if event.get("type") == "session.closed":
            raise RuntimeError(
                f"Live session closed unexpectedly: {event.get('reason')}."
            )


@asynccontextmanager
async def audio_clock(connection: AsyncBetaLiveConnection) -> AsyncIterator[None]:
    """Advance the Live timeline while waiting for appended-context acknowledgements."""

    async def send_silence() -> None:
        while True:
            await asyncio.wait_for(
                connection.session.input_audio.append(audio=bytes(FRAME_BYTES)),
                EVENT_TIMEOUT,
            )
            await asyncio.sleep(0.05)

    sender = asyncio.create_task(send_silence())
    try:
        yield
    finally:
        if not sender.done():
            sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass


async def close_session(
    connection: AsyncBetaLiveConnection,
    *,
    on_started: Callable[[models.LiveServerEventLiveSessionStarted], None]
    | None = None,
) -> None:
    """A closed socket is not proof of finalization; require session.closed."""
    deadline = time.monotonic() + CLOSE_TIMEOUT
    try:
        await asyncio.wait_for(
            connection.session.close(event_id=f"close-{uuid4().hex[:8]}"), CLOSE_TIMEOUT
        )
        while True:
            event = await receive(connection, deadline)
            if (
                isinstance(event, models.LiveServerEventLiveSessionStarted)
                and on_started is not None
            ):
                on_started(event)
            if event.get("type") == "session.closed":
                if not isinstance(event, models.LiveServerEventLiveSessionClosed):
                    raise RuntimeError("Expected the SDK's typed session.closed event.")
                if event.get("reason") != "close_requested":
                    raise RuntimeError(
                        f"Live did not close normally: {event.get('reason')}."
                    )
                print("Confirmed session.closed: close_requested.")
                return
    finally:
        pending = _PENDING_READS.pop(connection, None)
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


@asynccontextmanager
async def live_session(
    project: AIProjectClient,
    cleanup: AsyncExitStack,
    agent: models.AgentVersionDetails,
    *,
    store: bool = False,
) -> AsyncIterator[
    tuple[AsyncBetaLiveConnection, models.LiveServerEventLiveSessionStarted]
]:
    conversation_ids: set[str] = set()

    def remember_conversation(
        started: models.LiveServerEventLiveSessionStarted,
    ) -> None:
        identifier = started.conversation_id
        if store and identifier and identifier not in conversation_ids:
            cleanup.push_async_callback(
                delete_owned_conversation, project, agent.name, identifier
            )
            conversation_ids.add(identifier)

    async with project.beta.voice_agents.live.connect(
        agent_name=agent.name, agent_version=agent.version, store=store
    ) as connection:
        try:
            # Foundry starts the session from the saved definition. Never send session.start.
            started = await wait_event(connection, "session.started")
            if not isinstance(started, models.LiveServerEventLiveSessionStarted):
                raise RuntimeError("Expected the SDK's typed session.started event.")
            remember_conversation(started)
            if store and not started.conversation_id:
                raise RuntimeError(
                    "Stored Live session omitted session.started.conversation_id."
                )
            yield connection, started
        finally:
            # A late startup event can still identify an owned conversation after an earlier error.
            await close_session(connection, on_started=remember_conversation)
