"""HTTP host for the resilient Copilot agent (invocations protocol).

Endpoints
---------
``POST /invocations``  body ``{"input": "...", "mode": "immediate"|"enqueue"?}``
    * No active turn on this session → starts (or resumes) the resilient task.
    * Active turn on this session → delivers the input to the *live* Copilot
      session as steering (``mode="immediate"``, redirects the current turn) or
      queued follow-up (``mode="enqueue"``). This is Copilot's native
      multi-input control, not the framework's cancel-and-re-enter queue.
    Returns ``202`` with ``{invocation_id, session_id, task_id, action}`` or a
    live SSE stream when ``Accept: text/event-stream`` is set.

``GET /invocations/{id}``
    * ``Accept: text/event-stream`` (+ optional ``?last_event_id=N``) →
      reconnectable SSE; the file-backed replay serves the gap after a client
      drop or a container crash before live-tailing.
    * Otherwise → JSON snapshot of the task's status / metadata.

``POST /elicit``  body ``{"session_id","elicitation_id","action","content"?}``
    Answers a human-in-the-loop pause. If the elicitation is still parked in
    this process, the answer resolves it directly; if it was raised in a
    pre-crash lifetime (no live Future), the answer is delivered to the resumed
    session as a normal message so the human's decision is not lost.

``POST /invocations/{id}/cancel``
    Aborts the in-flight Copilot turn and cooperatively winds down the task.

Streaming wiring: ``streams.use_file_backed_replay(...)`` is registered once at
import so per-turn events persist to disk and survive a container crash;
``cursor_fn`` reads each event's ``sequence_number`` so ``?last_event_id=N``
reconnects skip exactly what the client already received.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from dotenv import load_dotenv

# Local modules construct environment-dependent snapshot/crash configuration at
# import time, so load .env before importing them.
load_dotenv(override=False)

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from azure.ai.agentserver.core.streaming import (
    EventStream,
    EventStreamNotFoundError,
    streams,
)
from azure.ai.agentserver.core.tasks import set_resilient_tasks_enabled
from azure.ai.agentserver.invocations import InvocationAgentServerHost

try:
    from .agent import (
        copilot_agent,
        fail_harness_start,
        get_invocation_status,
        mark_client_cancel,
        reserve_harness,
        submit_elicitation_decision,
        submit_native_input,
    )
    from .copilot_session import CopilotHarness
    from .store import validate_session_id
except ImportError:  # allow `python main.py` from inside this directory
    from agent import (
        copilot_agent,
        fail_harness_start,
        get_invocation_status,
        mark_client_cancel,
        reserve_harness,
        submit_elicitation_decision,
        submit_native_input,
    )
    from copilot_session import CopilotHarness
    from store import validate_session_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Per-turn streams persist to disk so they survive a container crash + restart.
# cursor_fn reads the agent's sequence_number so ?last_event_id=N reconnects
# skip already-delivered events.
streams.use_file_backed_replay(cursor_fn=lambda ev: ev["sequence_number"])

app = InvocationAgentServerHost()

# Opt into resilient-task startup recovery so a restarted container re-invokes
# in-flight tasks with ctx.entry_mode == "recovered".
set_resilient_tasks_enabled(True)


def _task_id(session_id: str) -> str:
    return f"copilot-{validate_session_id(session_id)}"


_INPUT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ELICITATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MISSING = object()


def _validate_input_id(value: Any = _MISSING) -> str:
    if value is _MISSING:
        return str(uuid.uuid4())
    if not isinstance(value, str) or not _INPUT_ID_RE.fullmatch(value):
        raise ValueError(
            "input_id must be 1-128 ASCII letters, digits, underscores, or hyphens"
        )
    return value


def _invalid_session_response(exc: ValueError) -> JSONResponse:
    return JSONResponse(
        {"error": "invalid_request", "message": str(exc)}, status_code=400
    )


def _validate_elicitation_id(value: Any) -> str:
    if not isinstance(value, str) or not _ELICITATION_ID_RE.fullmatch(value):
        raise ValueError(
            "elicitation_id must be 1-128 ASCII letters, digits, underscores, or hyphens"
        )
    return value


def _request_prompt(data: dict[str, Any]) -> str:
    for field in ("input", "prompt", "message", "query"):
        if field not in data:
            continue
        value = data[field]
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        return value.strip()
    return ""


def _session_id(request: Request) -> str:
    """Resolve the session id on any route (falls back to a query param)."""
    return request.query_params.get("agent_session_id") or getattr(
        request.state, "session_id", ""
    )


# --- SSE rendering ---------------------------------------------------------


async def _sse_from_stream(
    stream: EventStream,
    invocation_id: str,
    *,
    skip_after: int | None = None,
) -> AsyncGenerator[bytes, None]:
    """Render a stream's events as SSE bytes; each id is the reconnect cursor."""
    try:
        async for chunk in stream.subscribe(after=skip_after):
            seq = chunk.get("sequence_number", "")
            yield f"id: {seq}\ndata: {json.dumps(chunk)}\n\n".encode()
        done = {"type": "done", "invocation_id": invocation_id}
        yield f"event: done\ndata: {json.dumps(done)}\n\n".encode()
    except EventStreamNotFoundError:
        superseded = {"type": "superseded", "invocation_id": invocation_id}
        yield f"event: superseded\ndata: {json.dumps(superseded)}\n\n".encode()


# --- Invocation handlers ---------------------------------------------------


@app.invoke_handler
async def handle_invoke(request: Request) -> Response:
    """Start / resume a turn, or steer / queue a live one."""
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
        if not isinstance(data, dict):
            raise ValueError("body is not a JSON object")
    except (json.JSONDecodeError, ValueError):
        data = {}
    try:
        prompt = _request_prompt(data)
    except ValueError as exc:
        return _invalid_session_response(exc)
    if not prompt:
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": 'Request body must be a JSON object with a non-empty "input" string.',
            },
            status_code=400,
        )
    mode = data.get("mode")
    if mode not in (None, "immediate", "enqueue"):
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": 'mode must be "immediate" or "enqueue".',
            },
            status_code=400,
        )

    invocation_id: str = request.state.invocation_id
    try:
        session_id = validate_session_id(str(request.state.session_id))
        input_id = _validate_input_id(
            data["input_id"] if "input_id" in data else _MISSING
        )
        task_id = _task_id(session_id)
    except ValueError as exc:
        return _invalid_session_response(exc)

    # The live task consumer durably journals the input before native Copilot
    # delivery and acknowledges only after a live snapshot is saved.
    try:
        delivered = await submit_native_input(
            session_id, input_id, prompt, mode or "enqueue"
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "input_rejected", "message": str(exc)}, status_code=409
        )
    if delivered is not None:
        return JSONResponse(
            {
                **delivered,
                "action": "steer" if mode == "immediate" else "queue",
                "session_id": session_id,
            },
            status_code=202,
        )

    # No readied live harness (including closing/idle races): start or queue a
    # framework-durable turn instead of touching a missing Copilot session.
    slot = reserve_harness(session_id)
    try:
        stream = await streams.get_or_create(invocation_id)
        await copilot_agent.start(
            task_id=task_id,
            input={
                "prompt": prompt,
                "session_id": session_id,
                "invocation_id": invocation_id,
                "call_id": getattr(request.state, "call_id", None),
                "input_id": input_id,
                "mode": mode,
            },
        )
    except BaseException as exc:
        fail_harness_start(session_id, exc, slot)
        raise

    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(
            _sse_from_stream(stream, invocation_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return JSONResponse(
        {
            "status": "started",
            "action": "start",
            "invocation_id": invocation_id,
            "session_id": session_id,
            "task_id": task_id,
            "input_id": input_id,
        },
        status_code=202,
    )


@app.get_invocation_handler
async def handle_get(request: Request) -> Response:
    """Stream (reconnectable) OR poll the per-invocation state."""
    invocation_id: str = request.state.invocation_id

    if "text/event-stream" in request.headers.get("accept", ""):
        raw = request.query_params.get("last_event_id", "") or request.headers.get(
            "last-event-id", ""
        )
        skip_after: int | None = int(raw) if raw.isdigit() else None
        try:
            stream = await streams.get(invocation_id)
        except EventStreamNotFoundError:
            return JSONResponse(
                {
                    "status": "not_found",
                    "message": "No live stream for this invocation id.",
                },
                status_code=404,
            )
        return StreamingResponse(
            _sse_from_stream(stream, invocation_id, skip_after=skip_after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    status = await get_invocation_status(invocation_id)
    if status is None:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return JSONResponse(
        {
            "task_id": status.get("task_id"),
            "invocation_id": status.get("invocation_id"),
            "status": status.get("status"),
            "task_status": status.get("task_status"),
            "payload": status.get("payload"),
        }
    )


@app.cancel_invocation_handler
async def handle_cancel(request: Request) -> Response:
    """Abort the in-flight Copilot turn and wind the task down."""
    session_id = _session_id(request)
    if not session_id:
        return JSONResponse(
            {
                "status": "not_found",
                "message": "Provide ?agent_session_id=<id>.",
            }
        )
    try:
        session_id = validate_session_id(session_id)
    except ValueError as exc:
        return _invalid_session_response(exc)
    invocation_id: str = request.state.invocation_id
    invocation = await get_invocation_status(invocation_id)
    if invocation is None or invocation.get("status") != "running":
        return JSONResponse(
            {
                "status": "not_found",
                "message": "No active task for this invocation.",
            }
        )
    expected_task_id = _task_id(session_id)
    if invocation.get("task_id") != expected_task_id:
        return JSONResponse(
            {
                "status": "not_found",
                "message": "Invocation does not belong to the supplied session.",
            }
        )
    framework_input_id = invocation.get("framework_input_id")
    if not isinstance(framework_input_id, str) or not framework_input_id:
        return JSONResponse(
            {
                "status": "not_found",
                "message": (
                    "Invocation has no exact framework input identity and cannot "
                    "be cancelled safely."
                ),
            }
        )
    run = await copilot_agent.get_active_run(
        expected_task_id,
        framework_input_id,
    )
    if run is None:
        return JSONResponse(
            {
                "status": "not_found",
                "message": "No active task to cancel.",
            }
        )
    mark_client_cancel(session_id)
    await run.cancel()
    return JSONResponse(
        {"status": "cancelled", "message": "Task cancellation requested."}
    )


async def handle_elicit(request: Request) -> Response:
    """Answer a human-in-the-loop elicitation pause.

    Body: ``{"session_id","elicitation_id","action","content"?}`` where
    ``action`` is ``"accept" | "decline" | "cancel"``.
    """
    try:
        data = await request.json()
        session_id = validate_session_id(data["session_id"])
        if not hasattr(request.state, "session_id"):
            request.state.session_id = (
                app.config.session_id or request.query_params.get("agent_session_id")
            )
        caller_session_id = validate_session_id(request.state.session_id)
        elicitation_id = _validate_elicitation_id(data["elicitation_id"])
        action = str(data.get("action", "accept"))
        content = data.get("content")
    except ValueError as exc:
        return _invalid_session_response(exc)
    except (json.JSONDecodeError, KeyError, TypeError):
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": (
                    'Body must include "session_id" and "elicitation_id" '
                    '(and usually "action"/"content").'
                ),
            },
            status_code=400,
        )
    if session_id != caller_session_id:
        return JSONResponse(
            {
                "error": "forbidden",
                "message": "session_id must match the caller's resolved session.",
            },
            status_code=403,
        )
    if action not in ("accept", "decline", "cancel"):
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": "action must be accept, decline, or cancel.",
            },
            status_code=400,
        )
    if content is not None and not isinstance(content, dict):
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": "content must be a JSON object when provided.",
            },
            status_code=400,
        )

    try:
        result = await submit_elicitation_decision(
            session_id, elicitation_id, action, content
        )
    except ValueError as exc:
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)}, status_code=409
        )
    if result is not None:
        return JSONResponse(result)
    return JSONResponse(
        {
            "status": "no_pending_elicitation",
            "message": "No active durable task is accepting this elicitation decision.",
        },
        status_code=409,
    )


app.add_route("/elicit", handle_elicit, methods=["POST"])


if __name__ == "__main__":
    if not CopilotHarness.has_backend():
        import sys

        sys.exit(
            "Error: Set GITHUB_TOKEN (Copilot model) or FOUNDRY_PROJECT_ENDPOINT + "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME (BYOK Foundry model)."
        )
    app.run()
