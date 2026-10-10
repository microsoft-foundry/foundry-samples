"""The resilient Copilot task — long-running, crash-recoverable, steerable, HITL.

A single ``@multi_turn_task`` supervises the lifecycle of one GitHub Copilot
session. The Copilot SDK is the real agent brain (model + tool loop); this task
is the *durable host* around it. It provides exactly what the Copilot SDK does
not:

* **Long-running / no-ingress survival** — while the Copilot agent grinds
  through a (possibly minutes-long) tool loop, the task is ``in_progress``, so
  the platform keeps the container alive even with the client disconnected.
* **Crash recovery** — on a restarted container the framework re-invokes this
  task with ``ctx.entry_mode == "recovered"``; we call ``resume_session`` (the
  Copilot CLI persisted the workspace to disk) instead of creating a new one,
  emit a ``recovered`` marker onto the SAME file-backed stream, and re-drive
  the turn so it completes.
* **Reconnectable streaming** — every Copilot ``SessionEvent`` is emitted onto
  a file-backed replay stream with a monotonic ``sequence_number``; a client
  that dropped reconnects via ``?last_event_id=N`` and sees the gap with no
  loss (``main.py``).
* **Durable HITL marker** — when the model raises an elicitation, we persist a
  marker in an explicit ``FoundryStateStore`` so the human-in-the-loop pause is
  re-drivable after a crash even though the in-memory Future is gone.

Steering (``send(mode="immediate")``) and queueing (``send(mode="enqueue")``)
are delivered *directly to the live Copilot session* from ``main.py`` while a
turn is in flight — Copilot supports graceful intra-turn redirection natively,
so we do not route them through the framework's cancel-and-re-enter steering
queue. The task ``start()`` is used only to begin a turn (fresh) or to resume
the conversation on a later turn / after a crash.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pathlib import Path

from azure.ai.agentserver.core import resolve_state_subdir
from azure.ai.agentserver.core.storage import FoundryStateStore
from azure.ai.agentserver.core.streaming import streams
from azure.ai.agentserver.core.tasks import TaskContext, multi_turn_task

try:
    from .copilot_session import CopilotHarness
    from .store import SessionSnapshotStore
except ImportError:  # allow `python main.py` from inside this directory
    from copilot_session import CopilotHarness
    from store import SessionSnapshotStore

logger = logging.getLogger(__name__)


def session_state_store_name(session_id: str) -> str:
    """Name of the FoundryStateStore holding this session's small markers.

    ``ctx.metadata`` was removed from the resilient-task primitive, so durable
    application state (here: the pending-elicitation marker and the
    snapshot-exists flag) lives in an explicit conversation-scoped
    ``FoundryStateStore`` instead.
    """
    return f"copilot-state-{session_id}"


# Live harnesses keyed by session id, so the HTTP layer can deliver steering /
# queued inputs and elicitation answers to the in-flight Copilot session.
_HARNESSES: dict[str, CopilotHarness] = {}

# Durable snapshot store for the Copilot session workspace (StateStore-backed on
# hosted, file fallback offline). Makes the conversation survive a container
# REPLACEMENT, not just an in-process restart. See store.py.
_SNAPSHOT_STORE = SessionSnapshotStore(resolve_state_subdir("copilot-snapshots"))

# Root under which each session's Copilot config_dir lives (one isolated
# SQLite session store per session id). Kept under the shared, operator-managed
# state root so it sits alongside the framework's tasks/ and streams/.
_CONFIG_ROOT = resolve_state_subdir("copilot-sessions")


def _config_dir_for(session_id: str) -> Path:
    """Per-session Copilot config_dir (its own SQLite store + session-state)."""
    return _CONFIG_ROOT / session_id


# Optional local crash simulation: after this many events are emitted, hard-crash
# (os._exit) so a restart exercises the resume_session() recovery path. A real
# SIGKILL/OOM is identical from the task's perspective. Unset in production.
_SIMULATE_CRASH_AFTER_EVENTS = int(os.environ.get("SIMULATE_CRASH_AFTER_EVENTS", "-1"))


def get_harness(session_id: str) -> CopilotHarness | None:
    """Return the live harness for a session, if a turn is currently active."""
    return _HARNESSES.get(session_id)


def _event_payload(event: Any) -> dict:
    """Render a Copilot SessionEvent as a stream payload (cursor added by emit)."""
    try:
        body = event.to_dict()
    except Exception:  # pylint: disable=broad-except
        body = {"type": str(getattr(event, "type", "unknown"))}
    return {"kind": "copilot_event", **body}


@multi_turn_task(name="copilot_agent", steerable=True)
async def copilot_agent(ctx: TaskContext[dict]) -> None:
    """Supervise one Copilot turn end-to-end with full resilience.

    Input: ``{"prompt": str, "session_id": str, "invocation_id": str,
    "call_id": str | None}``. Progress is read from the per-turn SSE stream, not
    the task's return value; the body returns ``None`` so the steerable chain
    stays alive for subsequent turns.
    """
    session_id: str = ctx.input["session_id"]
    inv_id: str = ctx.input["invocation_id"]
    prompt: str = ctx.input["prompt"]
    recovered = ctx.entry_mode == "recovered"
    config_dir = _config_dir_for(session_id)

    # Durable session markers (pending elicitation + snapshot-exists flag) live
    # in an explicit FoundryStateStore now that ctx.metadata is gone. It uses a
    # local file-backed fallback automatically when not hosted, so it also works
    # offline. Load the current markers once; persist on change.
    state_store = await FoundryStateStore.get_or_create(
        session_state_store_name(session_id),
        description="Copilot session markers (pending elicitation, snapshot ref)",
    )
    state_item = await state_store.get_item("state")
    state: dict = (
        dict(state_item.value)
        if state_item is not None and isinstance(state_item.value, dict)
        else {}
    )

    stream = await streams.get_or_create(inv_id)
    # On recovery, last_cursor() is the highest sequence_number that reached
    # disk before the crash, so the client's reconnect skips nothing.
    last_cursor = await stream.last_cursor()
    seq = last_cursor or 0

    async def emit(payload: dict) -> None:
        nonlocal seq
        seq += 1
        await stream.emit({"sequence_number": seq, **payload})

    harness = CopilotHarness()
    _HARNESSES[session_id] = harness

    async def on_elicit_request(
        elicitation_id: str, message: str, schema: dict
    ) -> None:
        # Persist a durable marker so a crash while parked on this elicitation
        # is re-drivable in the next lifetime (the in-memory Future is not).
        state["pending_elicitation"] = {
            "elicitation_id": elicitation_id,
            "message": message,
            "schema": schema,
        }
        await state_store.set_item("state", state)
        await emit(
            {
                "type": "elicitation_request",
                "elicitation_id": elicitation_id,
                "message": message,
                "schema": schema,
            }
        )

    try:
        await emit(
            {
                "type": "turn_start",
                "session_id": session_id,
                "entry_mode": ctx.entry_mode,
                "recovery_count": ctx.recovery_count,
            }
        )

        # CONTAINER-DURABLE RECOVERY: on a recovered re-entry the local disk may
        # be gone (container replacement), so restore the last good Copilot
        # session snapshot from the durable StateStore INTO config_dir before
        # resume_session reads it. On a fresh turn nothing is restored.
        if recovered:
            await _SNAPSHOT_STORE.restore(session_id, config_dir)

        # Resume whenever a session store is present on disk (either a
        # same-container follow-up turn, or one we just restored); otherwise
        # this is the first turn for the session and we create it fresh.
        have_session = (config_dir / "session-store.db").exists()
        await harness.start(
            session_id,
            recover=have_session,
            on_elicit_request=on_elicit_request,
            config_directory=str(config_dir),
        )

        if recovered:
            await emit({"type": "recovered", "recovery_count": ctx.recovery_count})
            pending = state.get("pending_elicitation")
            if pending:
                # Re-surface the unanswered question so a reconnecting client
                # knows we are still waiting on them (see README caveat).
                await emit(
                    {"type": "elicitation_request", "recovered": True, **pending}
                )

        # Deliver the prompt. On recovery we re-drive the same prompt: the
        # Copilot conversation history is restored by resume_session, so the
        # model continues in context (some streamed content may repeat, but the
        # stream has no gap — see README "Crash recovery").
        await harness.send(prompt)

        # When cancel/shutdown fires while the pump is blocked waiting for the
        # next event, abort the Copilot turn so the agent winds down and the
        # pump unblocks. The in-loop check below handles the case where the
        # signal arrives between events.
        async def _watch_stop() -> None:
            done, pending = await asyncio.wait(
                {
                    asyncio.create_task(ctx.cancel.wait()),
                    asyncio.create_task(ctx.shutdown.wait()),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await harness.abort()

        watcher = asyncio.create_task(_watch_stop())

        try:
            async for event in harness.events():
                if ctx.cancel.is_set() or ctx.shutdown.is_set():
                    break
                await emit(_event_payload(event))
                _maybe_crash(seq)
        finally:
            watcher.cancel()

        clean_completion = not (ctx.cancel.is_set() or ctx.shutdown.is_set())
        if not clean_completion:
            await harness.abort()
            await emit({"type": "cancelled"})
        else:
            await emit({"type": "turn_complete"})
            # Turn finished cleanly — clear any answered elicitation marker.
            if state.get("pending_elicitation"):
                state["pending_elicitation"] = None
                await state_store.set_item("state", state)

        # DURABLE SNAPSHOT: stop the Copilot client first so the SQLite WAL is
        # checkpointed and the on-disk session store is consistent, THEN copy
        # config_dir into the StateStore so the conversation survives a
        # container replacement. Keep only a tiny reference in the state store.
        await harness.close()
        try:
            await _SNAPSHOT_STORE.save(session_id, config_dir)
            state["has_snapshot"] = True
            await state_store.set_item("state", state)
        except Exception:  # pylint: disable=broad-except
            logger.exception("failed to snapshot Copilot session %s", session_id)

        # Close the wire stream so SSE subscribers see the terminator. NOT done
        # on the crash path below: the stream must stay open for the recovery
        # re-entry to continue emitting to the same cursor with no gap.
        await stream.close()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("copilot_agent turn failed; emitting terminal frame")
        try:
            await emit(
                {
                    "type": "turn_failed",
                    "error": {"type": type(exc).__name__, "message": str(exc)[:2000]},
                }
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("failed to emit terminal turn_failed frame")
        # Close on a logical failure so subscribers fast-fail. A true crash
        # (os._exit/SIGKILL) never reaches here, so its stream stays open for
        # the recovery re-entry.
        try:
            await stream.close()
        except Exception:  # pylint: disable=broad-except
            pass
        raise
    finally:
        await harness.close()
        try:
            await state_store.aclose()
        except Exception:  # pylint: disable=broad-except
            pass
        _HARNESSES.pop(session_id, None)


def _maybe_crash(emitted: int) -> None:
    """Hard-crash after N emitted events when the crash hook is armed."""
    if 0 <= _SIMULATE_CRASH_AFTER_EVENTS <= emitted:
        logger.warning(
            "SIMULATE_CRASH_AFTER_EVENTS=%d reached (emitted=%d); os._exit(1).",
            _SIMULATE_CRASH_AFTER_EVENTS,
            emitted,
        )
        os._exit(1)
