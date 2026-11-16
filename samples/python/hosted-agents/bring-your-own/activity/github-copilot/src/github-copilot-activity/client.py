# Copyright (c) Microsoft. All rights reserved.
"""GitHub Copilot SDK harness for the agent.

"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid

from azure.identity import DefaultAzureCredential
from copilot import (
    CopilotClient,
    PermissionHandler,
    ProviderConfig,
    SessionEventType,
    ToolSet,
)

import tools

logger = logging.getLogger("github-copilot.client")

# The Copilot SDK ships a coding-assistant system prompt by default. Replace it
# with a Teams-assistant persona so the model uses our to-do / file tools
# instead of behaving like a code agent.
_SYSTEM_MESSAGE = (
    "You are a warm, concise personal assistant inside Microsoft Teams "
    "and Microsoft 365 Copilot. "
    "You help the user manage a simple to-do list, read files they have "
    "shared in the chat, and create documents for them. When the user asks "
    "you to DO something (add a task, mark it done, read a shared file, write "
    "or generate a document), you MUST use the matching tool rather than only "
    "describing how. "
    "To create or generate a file for the user, create it yourself using your "
    "shell and python tools in your workspace: write the text directly for "
    "text formats (.txt, .md, .csv, .json, .html, code), or for .docx, .pptx, "
    "and .pdf install the library you need at runtime (for example "
    "`pip install python-docx python-pptx reportlab`) and use it to build the "
    "file. Then call the deliver_file tool with the file's path to send it. "
    "Never say you have created or attached a file unless you actually created "
    "it and called deliver_file in this turn. You cannot generate images. "
    "Prefer short, friendly replies. If you are unsure, ask a brief "
    "clarifying question."
)

_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
_MODEL = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")

_credential = DefaultAzureCredential()
_client: CopilotClient | None = None
# One Copilot SDK session per Teams/Copilot conversation, keyed by conversation id
_sessions: dict[str, tuple[object, str]] = {}
# Serialize turns: the Copilot SDK session processes one turn at a time, and
# channels like M365 Copilot can fire activities concurrently/in bursts. Without
# this lock, overlapping send_and_wait calls deadlock on "waiting for idle".
_turn_lock = asyncio.Lock()


def _fresh_token() -> str:
    return _credential.get_token("https://ai.azure.com/.default").token


def _sdk_session_id(conversation_id: str) -> str:
    """Derive a stable, short SDK session id from the conversation.

    The SDK session id doubles as the provider ``prompt_cache_key`` which has a
    64-char limit, so hash the (long) Teams/Copilot conversation id to a compact,
    stable token instead of embedding it raw.
    """
    if not conversation_id:
        return f"conv-{uuid.uuid4().hex}"
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:32]
    return f"conv-{digest}"


async def _get_session(conversation_id: str):
    """Create/reuse a per-conversation session, refreshing on token change."""
    global _client
    if not _ENDPOINT or not _MODEL:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME must be set."
        )
    if _client is None:
        _client = CopilotClient()
        await _client.start()

    # Token acquisition is blocking I/O; keep it off the event loop.
    token = await asyncio.to_thread(_fresh_token)
    # Reuse the conversation's session unless the bearer token rotated, so a
    # durable session never keeps calling the model with an expired token.
    cached = _sessions.get(conversation_id)
    if cached is not None and cached[1] == token:
        return cached[0]

    sid = _sdk_session_id(conversation_id)
    opts = dict(
        provider=ProviderConfig(
            type="azure",
            base_url=_ENDPOINT,
            wire_api="responses",
            bearer_token=token,
        ),
        model=_MODEL,
        tools=tools.build_tools(conversation_id),
        available_tools=ToolSet().add_builtin("*").add_custom("*"),
        system_message={"mode": "replace", "content": _SYSTEM_MESSAGE},
        on_permission_request=PermissionHandler.approve_all,
        streaming=True,
    )
    try:
        session = await _client.resume_session(sid, **opts)
        logger.info("Resumed Copilot session %s", sid)
    except Exception:  # pylint: disable=broad-exception-caught
        session = await _client.create_session(session_id=sid, **opts)
        logger.info("Created Copilot session %s", sid)
    _sessions[conversation_id] = (session, token)
    return session


async def _reset_session(conversation_id: str) -> None:
    """Drop a conversation's cached session so the next turn rebuilds it clean."""
    entry = _sessions.pop(conversation_id, None)
    if entry is not None:
        try:
            await entry[0].abort()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


# Friendly progress labels for the built-in / custom tools, shown to the user as
# transient "informative updates" while the model works (they vanish on the final
# streamed reply).
_TOOL_LABELS = {
    "add_task": "Adding your task…",
    "list_tasks": "Looking up your tasks…",
    "complete_task": "Marking the task done…",
    # built-in file tools the model uses to read shared files
    "view": "Reading the file…",
    "read_file": "Reading the file…",
    "bash": "Working with the file…",
    "grep": "Searching the file…",
    "glob": "Looking through the files…",
    "str_replace": "Editing the file…",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"Using {name.replace('_', ' ')}…")


async def ask_stream(conversation_id: str, text: str, files: list[dict[str, str]] | None = None):
    """Drive one turn and yield ``(kind, text)`` tuples as the model works.

    ``files`` is an optional list of ``{name, path}`` raw files to hand to the
    model as attachments — it reads/analyzes them itself (any type).

    ``kind`` is one of:
      - ``"progress"`` — a transient status line (tool activity); show + replace.
      - ``"delta"``    — an incremental chunk of the assistant's reply text.
      - ``"final"``    — the whole reply (only emitted when no deltas streamed,
                         e.g. an error string).
    """
    async with _turn_lock:  # one turn at a time — the SDK session isn't concurrent
        try:
            session = await _get_session(conversation_id)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            logger.error("ask_stream setup failed: %s", ex, exc_info=True)
            yield ("final", f"Sorry, something went wrong: {ex}")
            return

        attachments = []
        for f in (files or []):
            path = f.get("path")
            if not path:
                continue
            if f.get("kind") == "image" and f.get("mime"):
                # Inline image → base64 blob so the model can see it (vision).
                try:
                    import base64
                    with open(path, "rb") as fh:
                        data = base64.b64encode(fh.read()).decode("ascii")
                    attachments.append({
                        "type": "blob",
                        "data": data,
                        "mimeType": f["mime"],
                        "displayName": f.get("name", ""),
                    })
                except Exception as ex:  # pylint: disable=broad-exception-caught
                    logger.warning("could not encode image %s: %s", path, ex)
            else:
                attachments.append({"type": "file", "path": path, "displayName": f.get("name", "")})

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _on_event(ev):
            # May be invoked from the SDK's reader thread; hop to our loop safely.
            loop.call_soon_threadsafe(queue.put_nowait, ev)

        unsubscribe = session.on(_on_event)
        got_delta = False
        final_text = ""
        try:
            await session.send(text, attachments=attachments or None)  # dispatch the turn
            while True:
                ev = await asyncio.wait_for(queue.get(), timeout=90)
                etype = ev.type
                data = ev.data
                if etype == SessionEventType.TOOL_EXECUTION_START:
                    yield ("progress", _tool_label(getattr(data, "tool_name", "") or ""))
                elif etype == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                    chunk = getattr(data, "delta_content", "") or ""
                    if chunk:
                        got_delta = True
                        yield ("delta", chunk)
                elif etype == SessionEventType.ASSISTANT_MESSAGE:
                    final_text = getattr(data, "content", "") or final_text
                elif etype in (SessionEventType.SESSION_IDLE, SessionEventType.ASSISTANT_IDLE):
                    break
                elif etype == SessionEventType.SESSION_ERROR:
                    logger.error("session error event: %s", getattr(data, "__dict__", data))
                    if not got_delta:
                        yield ("final", "Sorry, I hit a problem answering that.")
                    break
        except asyncio.TimeoutError:
            logger.warning("ask_stream timed out; resetting session")
            await _reset_session(conversation_id)
            if not got_delta:
                yield ("final", "Sorry, that took too long. Please try again.")
            return
        except Exception as ex:  # pylint: disable=broad-exception-caught
            logger.error("ask_stream failed: %s", ex, exc_info=True)
            await _reset_session(conversation_id)
            if not got_delta:
                yield ("final", f"Sorry, something went wrong: {ex}")
            return
        finally:
            try:
                unsubscribe()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        if not got_delta:
            yield ("final", final_text.strip() or "(no response)")
