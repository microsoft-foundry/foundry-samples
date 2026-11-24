"""Shared helpers for the voice-agent samples in this folder."""

import asyncio
import os
import re
import sys
import time
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID, uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.aio import AIProjectClient as AsyncAIProjectClient
from azure.ai.projects.models import (
    PhoneNumber,
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseDone,
    RealtimeServerEventSessionCreated,
    TeamsAddress,
    TelephonyAddress,
    VoiceAgentDefinition,
    VoiceConversation,
    VoiceConversationStatus,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.core.exceptions import ResourceNotFoundError

# Seconds to wait for the agent's reply before giving up.
_RESPONSE_TIMEOUT: Final = 45

# Seconds to wait for the service to finish finalizing the conversation after the session ends,
# and how many times to poll before giving up.
_FINALIZE_POLL_INTERVAL: Final = 1
_FINALIZE_POLL_ATTEMPTS: Final = 15
PROVIDERS = ("twilio", "teams_phone_extensibility", "sip")


def sample_agent_name(prefix: str) -> str:
    """Use an explicitly supplied new name, or generate a unique sample-owned name."""
    return os.environ.get("FOUNDRY_VOICE_AGENT_NAME") or f"{prefix}-{uuid4().hex[:8]}"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} to your own resource/configuration value.")
    return value


def phone_number(value: str) -> PhoneNumber:
    if not re.fullmatch(r"\+[1-9][0-9]{1,14}", value):
        raise ValueError(
            "Phone numbers must use E.164, with '+' and at most 15 digits."
        )
    return PhoneNumber(value=value)


def source_address(provider: str, value: str) -> TelephonyAddress:
    if provider == "teams_phone_extensibility":
        identifier = UUID(value)
        if not identifier.int:
            raise ValueError(
                "The Teams resource-account object ID must be a nonempty GUID."
            )
        return TeamsAddress(value=str(identifier))
    if provider in ("twilio", "sip"):
        return phone_number(value)
    raise ValueError(f"Unsupported provider: {provider}")


def require_new_agent(client: AIProjectClient, agent_name: str) -> None:
    """Refuse to change an agent that already exists."""
    try:
        client.agents.get(agent_name=agent_name)
    except ResourceNotFoundError:
        return
    raise ValueError(
        f"Agent '{agent_name}' already exists. Choose an unused sample agent name."
    )


async def require_new_agent_async(
    client: AsyncAIProjectClient, agent_name: str
) -> None:
    """Refuse to change an agent that already exists, using the async client."""
    try:
        await client.agents.get(agent_name=agent_name)
    except ResourceNotFoundError:
        return
    raise ValueError(
        f"Agent '{agent_name}' already exists. Choose an unused sample agent name."
    )


def safe_print(text: str) -> None:
    """Print text that may contain characters the current console can't display.

    Model-generated replies and instructions can contain characters (curly quotes, em-dashes,
    etc.) outside some legacy, non-Unicode console encodings (for example when stdout is
    piped/redirected on Windows). Rather than crashing with UnicodeEncodeError, fall back to
    replacing just the unsupported characters; a real interactive UTF-8 console prints unaffected.

    :param text: The text to print.
    :type text: str
    """
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


def format_conversation_item(item: Mapping[str, Any]) -> str:
    """Format a stored open-union item, including unknown service-generated kinds."""
    parts = []
    for part in item.get("content") or []:
        text = part.get("transcript") or part.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    transcript = " ".join(parts)
    line = f"{item.get('role') or item['type']} id={item.get('id')}"
    return f"{line}: {transcript}" if transcript else line


def wait_for_conversation(
    client: AIProjectClient, agent_name: str, conversation_id: str
) -> VoiceConversation:
    """Wait for persisted content after the WebSocket closes, failing on storage errors."""
    for _ in range(_FINALIZE_POLL_ATTEMPTS):
        try:
            conversation = client.voice_agents.conversations.get(
                agent_name, conversation_id
            )
        except ResourceNotFoundError:
            # Content can briefly be absent while the closed session is being persisted.
            pass
        else:
            if conversation.status == VoiceConversationStatus.COMPLETED:
                return conversation
            if conversation.status == VoiceConversationStatus.FAILED:
                raise RuntimeError(f"Conversation {conversation_id} failed to persist.")
        time.sleep(_FINALIZE_POLL_INTERVAL)
    raise TimeoutError(f"Conversation {conversation_id} did not finish persisting.")


async def wait_for_conversation_async(
    client: AsyncAIProjectClient, agent_name: str, conversation_id: str
) -> VoiceConversation:
    """Wait for persisted content with the async client."""
    for _ in range(_FINALIZE_POLL_ATTEMPTS):
        try:
            conversation = await client.voice_agents.conversations.get(
                agent_name, conversation_id
            )
        except ResourceNotFoundError:
            pass
        else:
            if conversation.status == VoiceConversationStatus.COMPLETED:
                return conversation
            if conversation.status == VoiceConversationStatus.FAILED:
                raise RuntimeError(f"Conversation {conversation_id} failed to persist.")
        await asyncio.sleep(_FINALIZE_POLL_INTERVAL)
    raise TimeoutError(f"Conversation {conversation_id} did not finish persisting.")


def _finish_response(connection: RealtimeConnection) -> None:
    deadline = time.monotonic() + _RESPONSE_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for the voice response.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status != "completed":
                raise RuntimeError(
                    f"Voice response ended with status {event.response.status}."
                )
            return


def hold_sample_conversation(
    project_client: AIProjectClient,
    agent_name: str,
    prompt: str = "Say a short, friendly hello.",
) -> str:
    """Send one short realtime text turn to an existing voice agent and return the resulting
    persisted conversation id, once it has finished finalizing.

    Samples that read a conversation back (transcript, responses, audio) do not always have a
    live call handy to read. This helper produces a minimal real conversation on demand so those
    samples can run without requiring a conversation id up front. The agent named ``agent_name``
    must already exist (see voice_agent_basic.py) and be configured with ``store=True`` so
    its conversations are persisted. For a full interactive conversation and a fuller explanation
    of the realtime event flow used here, see voice_agent_realtime_text_conversation.py.

    :param project_client: The Foundry project client.
    :param agent_name: The name of an existing voice agent, configured with ``store=True``.
    :param prompt: The single text turn to send.
    :type project_client: ~azure.ai.projects.AIProjectClient
    :type agent_name: str
    :type prompt: str
    :return: The persisted conversation id.
    :rtype: str
    :raises RuntimeError: If the session ends without a persisted conversation id, the service
     reports a session error, or the conversation does not finish finalizing in time.
    """
    definition = project_client.agents.get(
        agent_name=agent_name
    ).versions.latest.definition
    if not isinstance(definition, VoiceAgentDefinition):
        raise TypeError(
            "Conversation readback needs a Realtime voice agent, not a GPT Live agent."
        )
    conversation_id = None
    succeeded = False
    try:
        with project_client.voice_agents.realtime.connect(
            agent_name=agent_name
        ) as conn:
            deadline = time.monotonic() + _RESPONSE_TIMEOUT
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for session.created.")
                event = conn.recv(timeout=remaining)
                if isinstance(event, RealtimeServerEventError):
                    raise RuntimeError(event.error.message)
                if isinstance(event, RealtimeServerEventSessionCreated):
                    conversation_id = event.conversation_id
                    break
            if not conversation_id:
                raise RuntimeError(
                    "The agent must have store=True to persist this conversation."
                )
            if definition.greeting is not None:
                _finish_response(conn)
            conn.conversation.item.create(
                item=RealtimeConversationItemMessageUser(
                    type=RealtimeConversationItemType.MESSAGE,
                    content=[
                        RealtimeConversationItemMessageUserContent(
                            type="input_text", text=prompt
                        )
                    ],
                )
            )
            conn.response.create()
            _finish_response(conn)
        wait_for_conversation(project_client, agent_name, conversation_id)
        succeeded = True
        return conversation_id
    finally:
        # A caller cannot clean an ID that was never returned after a failed turn.
        if conversation_id and not succeeded:
            project_client.voice_agents.conversations.delete(
                agent_name, conversation_id
            )
