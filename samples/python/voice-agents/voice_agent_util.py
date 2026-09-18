"""Shared helpers for the voice-agent samples in this folder."""

import sys
import time
from typing import Final

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItem,
    RealtimeConversationItemMessageAssistant,
    RealtimeConversationItemMessageSystem,
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseDone,
    RealtimeServerEventSessionCreated,
    VoiceConversationStatus,
)

# Seconds to wait for the agent's reply before giving up.
_RESPONSE_TIMEOUT: Final = 45

# Seconds to wait for the service to finish finalizing the conversation after the session ends,
# and how many times to poll before giving up.
_FINALIZE_POLL_INTERVAL: Final = 1
_FINALIZE_POLL_ATTEMPTS: Final = 15

# The concrete message-item subtypes that carry displayable transcript content. Other item kinds
# (function calls, MCP tool activity, etc.) are typed too but have no user-facing text to show.
_MESSAGE_ITEM_TYPES = (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageAssistant,
    RealtimeConversationItemMessageSystem,
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


def format_conversation_item(item: RealtimeConversationItem) -> str:
    """Format one persisted conversation item as a single display line.

    ``RealtimeConversationItem`` is a typed, discriminated union. Only message items (user,
    assistant, and system turns) carry displayable text, in their typed ``content`` parts; other
    item kinds (function calls, MCP activity, etc.) show just their id and type.

    :param item: One item returned by ``conversations.list_items()`` or ``conversations.get_item()``.
    :type item: ~azure.ai.projects.models.RealtimeConversationItem
    :return: A display line such as ``"assistant id=msg_123: Hello there"``.
    :rtype: str
    """
    if not isinstance(item, _MESSAGE_ITEM_TYPES):
        return f"{item.type} id={getattr(item, 'id', None)}"

    # Audio turns carry their spoken text as ``transcript`` (system-message content has no
    # ``transcript`` field, hence the getattr); typed-text turns carry it as ``text``.
    parts = [getattr(part, "transcript", None) or part.text or "" for part in item.content]
    transcript = " ".join(p.strip() for p in parts if p)
    line = f"{item.role} id={item.id}"
    return f"{line}: {transcript}" if transcript else line


def hold_sample_conversation(
    project_client: AIProjectClient, agent_name: str, prompt: str = "Say a short, friendly hello."
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
    conversation_id = None
    with project_client.beta.voice_agents.realtime.connect(agent_name=agent_name) as conn:
        conn.conversation.item.create(
            item=RealtimeConversationItemMessageUser(
                type=RealtimeConversationItemType.MESSAGE,
                content=[RealtimeConversationItemMessageUserContent(type="input_text", text=prompt)],
            )
        )
        conn.response.create()
        while True:
            event = conn.recv(timeout=_RESPONSE_TIMEOUT)
            if isinstance(event, RealtimeServerEventSessionCreated):
                # The persisted conversation id (only present when conversation persistence is
                # enabled) is set here, not on response.done.
                conversation_id = event.conversation_id or conversation_id
            if isinstance(event, RealtimeServerEventResponseDone):
                break
            if isinstance(event, RealtimeServerEventError):
                raise RuntimeError(f"Session error while holding a sample conversation: {event.error.message}")

    if not conversation_id:
        raise RuntimeError(
            "The realtime session ended without a persisted conversation id. Make sure the agent "
            "was configured with `store=True`."
        )

    # `response.done` only means the model finished replying, not that the service has finished
    # persisting the conversation -- immediately after the session closes, the conversation can
    # still briefly report `in_progress` while that finalization completes in the background.
    # Poll until it settles so callers can read a complete transcript right away.
    conversations = project_client.beta.voice_agents.conversations
    for _ in range(_FINALIZE_POLL_ATTEMPTS):
        conversation = conversations.get(agent_name, conversation_id)
        if conversation.status != VoiceConversationStatus.IN_PROGRESS:
            break
        time.sleep(_FINALIZE_POLL_INTERVAL)
    else:
        raise RuntimeError(
            f"Conversation {conversation_id} did not finish finalizing within "
            f"{_FINALIZE_POLL_ATTEMPTS * _FINALIZE_POLL_INTERVAL} seconds."
        )

    return conversation_id
