# Copyright (c) Microsoft. All rights reserved.

"""GitHub Copilot SDK hosted agent for Responses and VoiceLive."""

import asyncio
import logging
import os
import pathlib
import sys
import time
import uuid
from collections.abc import AsyncIterable
from types import SimpleNamespace
from typing import Any

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)
from azure.identity import DefaultAzureCredential
from copilot import CopilotClient, ProviderConfig
from copilot.session import PermissionHandler
from copilot.session_events import SessionEvent, SessionEventType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03dZ [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_VOICE_INSTRUCTION = (
    "[Voice mode] Respond in short, natural sentences as if speaking aloud. "
    "Do not use markdown, lists, code blocks, or special formatting. "
    "Keep the answer conversational and concise.\nUser input: "
)
_TOOL_LABELS = {
    "view": "Reading files",
    "glob": "Searching files",
    "grep": "Searching code",
    "powershell": "Running a command",
    "bash": "Running a command",
    "python": "Running Python",
    "node": "Running Node.js",
    "create": "Creating a file",
    "edit": "Editing a file",
    "report_intent": "Planning",
}

_client: CopilotClient | None = None
_session = None
_session_lock = asyncio.Lock()
_skills_dir = str(pathlib.Path(__file__).parent / "skills")


def _byok_provider() -> tuple[ProviderConfig | None, str | None]:
    """Create a Foundry provider when endpoint and model are configured."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
    if not endpoint or not model:
        return None, None

    token = DefaultAzureCredential().get_token(
        "https://ai.azure.com/.default"
    ).token
    provider = ProviderConfig(
        type="azure",
        base_url=endpoint,
        wire_api="responses",
        bearer_token=token,
    )
    return provider, model


async def _ensure_session():
    """Resume the hosted session or create it on the first request."""
    global _client, _session
    if _session is not None:
        return _session

    async with _session_lock:
        if _session is not None:
            return _session

        github_token = os.environ.get("GITHUB_TOKEN")
        # Token acquisition is blocking I/O; keep it off the event loop.
        provider, model = await asyncio.to_thread(_byok_provider)
        if provider:
            _client = CopilotClient()
            auth_mode = "foundry_byok"
        elif github_token:
            _client = CopilotClient(github_token=github_token)
            model = os.environ.get("GITHUB_COPILOT_MODEL")
            auth_mode = "github_token"
        else:
            raise RuntimeError(
                "Set FOUNDRY_PROJECT_ENDPOINT and "
                "AZURE_AI_MODEL_DEPLOYMENT_NAME for Foundry BYOK mode, "
                "or set GITHUB_TOKEN for GitHub Copilot mode."
            )

        logger.info("Starting Copilot client with auth_mode=%s", auth_mode)
        await _client.start()

        session_id = os.environ.get("FOUNDRY_AGENT_SESSION_ID") or str(uuid.uuid4())
        working_directory = str(pathlib.Path.home())
        session_options: dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "working_directory": working_directory,
        }
        if os.path.isdir(_skills_dir):
            session_options["skill_directories"] = [_skills_dir]
        if model:
            session_options["model"] = model
        if provider:
            session_options["provider"] = provider

        logger.info(
            "Opening Copilot session id=%s model=%s provider=%s",
            session_id,
            model or "(default)",
            "foundry" if provider else "github",
        )
        try:
            _session = await _client.resume_session(session_id, **session_options)
            logger.info("Resumed Copilot session id=%s", session_id)
        except Exception:
            _session = await _client.create_session(
                session_id=session_id,
                **session_options,
            )
            logger.info("Created Copilot session id=%s", session_id)
        return _session


def _stream_event_handler(
    queue: "asyncio.Queue[SimpleNamespace | Exception | None]",
    loop: asyncio.AbstractEventLoop,
):
    """Map Copilot session events to voice-friendly response chunks."""
    received_deltas = False
    last_tool_label = ""
    last_tool_time = 0.0

    def enqueue(item: SimpleNamespace | Exception | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def handler(event: SessionEvent) -> None:
        nonlocal received_deltas, last_tool_label, last_tool_time

        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                received_deltas = True
                enqueue(SimpleNamespace(text=delta, is_status=False))
            return

        if event.type == SessionEventType.ASSISTANT_MESSAGE:
            if received_deltas:
                enqueue(SimpleNamespace(message_done=True))
                received_deltas = False
                return
            content = getattr(event.data, "content", None)
            if content:
                enqueue(SimpleNamespace(text=content, is_status=False))
                enqueue(SimpleNamespace(message_done=True))
            return

        if event.type == SessionEventType.TOOL_EXECUTION_START:
            tool_name = (
                getattr(event.data, "tool_name", None)
                or getattr(event.data, "mcp_tool_name", None)
                or "tool"
            )
            label = _TOOL_LABELS.get(tool_name, f"Using {tool_name}")
            now = time.monotonic()
            if label != last_tool_label or now - last_tool_time >= 5:
                last_tool_label = label
                last_tool_time = now
                enqueue(SimpleNamespace(text=f"{label}...", is_status=True))
            return

        if event.type in {
            SessionEventType.TOOL_EXECUTION_PROGRESS,
            SessionEventType.TOOL_EXECUTION_COMPLETE,
        }:
            enqueue(SimpleNamespace(activity=True))
            return

        if event.type == SessionEventType.SESSION_IDLE:
            enqueue(None)
            return

        if event.type == SessionEventType.SESSION_ERROR:
            message = getattr(event.data, "message", None) or "Copilot session error"
            enqueue(RuntimeError(message))

    return handler


app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
) -> AsyncIterable[dict[str, Any]]:
    """Forward a Responses request to Copilot and stream its events."""
    user_input = await context.get_input_text() or "Hello!"
    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )
    yield stream.emit_created()
    yield stream.emit_in_progress()

    session = await _ensure_session()
    queue: asyncio.Queue[SimpleNamespace | Exception | None] = asyncio.Queue()
    unsubscribe = session.on(
        _stream_event_handler(queue, asyncio.get_running_loop())
    )

    current_item = None
    current_content = None

    async def open_item():
        nonlocal current_item, current_content
        current_item = stream.add_output_item_message()
        yield current_item.emit_added()
        current_content = current_item.add_text_content()
        yield current_content.emit_added()

    async def close_item():
        nonlocal current_item, current_content
        if current_content is not None:
            yield current_content.emit_text_done()
            yield current_content.emit_done()
        if current_item is not None:
            yield current_item.emit_done()
        current_item = None
        current_content = None

    send_task = asyncio.create_task(
        session.send(_VOICE_INSTRUCTION + user_input, mode="immediate")
    )
    try:
        while True:
            if cancellation_signal.is_set():
                send_task.cancel()
                async for event in close_item():
                    yield event
                yield stream.emit_incomplete(reason="cancelled")
                return

            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if send_task.done() and send_task.exception():
                    raise send_task.exception()
                continue

            if event is None:
                break
            if isinstance(event, Exception):
                raise event
            if getattr(event, "message_done", False):
                async for response_event in close_item():
                    yield response_event
                continue
            if getattr(event, "activity", False):
                continue

            text = getattr(event, "text", "")
            if not text:
                continue
            if getattr(event, "is_status", False):
                status_item = stream.add_output_item_message()
                yield status_item.emit_added()
                status_content = status_item.add_text_content()
                yield status_content.emit_added()
                yield status_content.emit_delta(f"{text}\n")
                yield status_content.emit_text_done()
                yield status_content.emit_done()
                yield status_item.emit_done()
                continue

            if current_item is None:
                async for response_event in open_item():
                    yield response_event
            yield current_content.emit_delta(text)

        await send_task
        yield stream.emit_completed()
    except Exception as exc:
        logger.exception("Copilot request failed")
        async for event in close_item():
            yield event
        err_item = stream.add_output_item_message()
        yield err_item.emit_added()
        err_content = err_item.add_text_content()
        yield err_content.emit_added()
        yield err_content.emit_delta(f"Sorry, something went wrong: {exc}")
        yield err_content.emit_text_done()
        yield err_content.emit_done()
        yield err_item.emit_done()
        yield stream.emit_completed()
        return
    finally:
        unsubscribe()
    logger.info("Completed Copilot Responses request id=%s", context.response_id)


if __name__ == "__main__":
    logger.info("Starting GitHub Copilot Responses VoiceLive agent")
    app.run()
