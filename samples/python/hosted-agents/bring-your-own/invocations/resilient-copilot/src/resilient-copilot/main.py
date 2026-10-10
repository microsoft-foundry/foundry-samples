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
from collections.abc import AsyncGenerator
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from dotenv import load_dotenv

from azure.ai.agentserver.core.streaming import (
    EventStream,
    EventStreamNotFoundError,
    streams,
)
from azure.ai.agentserver.core.tasks import set_resilient_tasks_enabled
from azure.ai.agentserver.invocations import InvocationAgentServerHost

try:
    from .agent import copilot_agent, get_harness
    from .copilot_session import CopilotHarness
except ImportError:  # allow `python main.py` from inside this directory
    from agent import copilot_agent, get_harness
    from copilot_session import CopilotHarness

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv(override=False)

# Per-turn streams persist to disk so they survive a container crash + restart.
# cursor_fn reads the agent's sequence_number so ?last_event_id=N reconnects
# skip already-delivered events.
streams.use_file_backed_replay(cursor_fn=lambda ev: ev["sequence_number"])

app = InvocationAgentServerHost()

# Opt into resilient-task startup recovery so a restarted container re-invokes
# in-flight tasks with ctx.entry_mode == "recovered".
set_resilient_tasks_enabled(True)


def _task_id(session_id: str) -> str:
    return f"copilot-{session_id}"


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
    prompt = str(
        data.get("input")
        or data.get("prompt")
        or data.get("message")
        or data.get("query")
        or ""
    ).strip()
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
    session_id: str = request.state.session_id
    task_id = _task_id(session_id)

    # If a turn is already live on this session, deliver the input straight to
    # the Copilot session (steering / queueing) rather than starting a new task.
    harness: CopilotHarness | None = get_harness(session_id)
    if harness is not None:
        await harness.send(prompt, mode=mode or "enqueue")
        return JSONResponse(
            {
                "status": "delivered",
                "action": "steer" if mode == "immediate" else "queue",
                "session_id": session_id,
            },
            status_code=202,
        )

    # No live turn — reserve this turn's stream BEFORE starting the task so a
    # late subscriber can still catch up from disk via ?last_event_id=N.
    stream = await streams.get_or_create(invocation_id)
    await copilot_agent.start(
        task_id=task_id,
        input={
            "prompt": prompt,
            "session_id": session_id,
            "invocation_id": invocation_id,
            "call_id": getattr(request.state, "call_id", None),
        },
    )

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

    # JSON snapshot (polling clients).
    session_id = _session_id(request)
    if not session_id:
        return JSONResponse(
            {"error": "Provide ?agent_session_id=<id> to locate the task."},
            status_code=404,
        )
    from azure.ai.agentserver.core.tasks._manager import (
        get_task_manager,
    )  # noqa: PLC0415

    mgr = get_task_manager()
    info: Any = await mgr.provider.get(_task_id(session_id))
    if info is None:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # NOTE: the session-marker FoundryStateStore is turn-scoped and cannot be
    # read from this poll route while a turn is active on hosted (the storage
    # API rejects it with a call_id mismatch -> 500), so the snapshot is derived
    # from the task record only — mirroring the SDK reference GET handler.
    _STATUS_MAP = {
        "in_progress": "running",
        "suspended": "completed",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }
    return JSONResponse(
        {
            "task_id": _task_id(session_id),
            "invocation_id": invocation_id,
            "status": _STATUS_MAP.get(info.status, info.status),
            "task_status": info.status,
            "payload": info.payload,
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
    from azure.ai.agentserver.core.tasks._manager import (
        get_task_manager,
    )  # noqa: PLC0415

    run = await get_task_manager().get_active_run(_task_id(session_id))
    if run is None:
        return JSONResponse(
            {
                "status": "not_found",
                "message": "No active task to cancel.",
            }
        )
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
        session_id = str(data["session_id"])
        elicitation_id = str(data["elicitation_id"])
        action = str(data.get("action", "accept"))
        content = data.get("content")
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
    if action not in ("accept", "decline", "cancel"):
        return JSONResponse(
            {
                "error": "invalid_request",
                "message": "action must be accept, decline, or cancel.",
            },
            status_code=400,
        )

    harness: CopilotHarness | None = get_harness(session_id)
    if harness is not None and harness.answer_elicitation(
        elicitation_id, action, content
    ):
        return JSONResponse({"status": "answered", "elicitation_id": elicitation_id})

    # No live Future (e.g. the elicitation was raised before a crash). Deliver
    # the human's decision to the resumed session as a normal message so it is
    # not lost; the model continues with the answer in context.
    if harness is not None and action == "accept" and content:
        await harness.send(f"[human input] {json.dumps(content)}")
        return JSONResponse(
            {"status": "delivered_as_message", "elicitation_id": elicitation_id}
        )
    return JSONResponse(
        {
            "status": "no_pending_elicitation",
            "message": "No live elicitation and nothing to deliver; the turn may have ended.",
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
