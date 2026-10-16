"""Resilient task supervisor for one durable GitHub Copilot session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from azure.ai.agentserver.core import resolve_state_subdir
from azure.ai.agentserver.core.storage import (
    FoundryStateStore,
    FoundryStorageNotFoundError,
)
from azure.ai.agentserver.core.streaming import streams
from azure.ai.agentserver.core.tasks import TaskContext, multi_turn_task

try:
    from .copilot_session import (
        CopilotHarness,
        ElicitationDecisionRequest,
        ElicitationRequest,
        HarnessClosingError,
        NativeInputRequest,
        TodoCheckpointDetectionFailure,
        TodoCheckpointRequest,
    )
    from .store import (
        InvocationStatusStore,
        SessionSnapshotStore,
        session_storage_key,
        validate_session_id,
    )
except ImportError:  # allow `python main.py` from inside this directory
    from copilot_session import (
        CopilotHarness,
        ElicitationDecisionRequest,
        ElicitationRequest,
        HarnessClosingError,
        NativeInputRequest,
        TodoCheckpointDetectionFailure,
        TodoCheckpointRequest,
    )
    from store import (
        InvocationStatusStore,
        SessionSnapshotStore,
        session_storage_key,
        validate_session_id,
    )

logger = logging.getLogger(__name__)

_SNAPSHOT_STORE = SessionSnapshotStore(resolve_state_subdir("copilot-snapshots"))
_INVOCATION_STORE = InvocationStatusStore(resolve_state_subdir("copilot-invocations"))
_CONFIG_ROOT = resolve_state_subdir("copilot-sessions")
_SIMULATE_CRASH_AFTER_EVENTS = int(os.environ.get("SIMULATE_CRASH_AFTER_EVENTS", "-1"))
_MAX_INPUT_JOURNAL_ENTRIES = 32
_MAX_INPUT_JOURNAL_BYTES = 512 * 1024
_READY_TIMEOUT_SECONDS = 15


def session_state_store_name(session_id: str) -> str:
    """Return a bounded store name for this session's durable control state."""
    return f"copilot-state-{session_storage_key(session_id)}"


def _legacy_session_state_store_name(session_id: str) -> str:
    return f"copilot-state-{validate_session_id(session_id)}"


def _config_dir_for(session_id: str) -> Path:
    """Return a confined per-session Copilot configuration directory."""
    return _CONFIG_ROOT / session_storage_key(session_id)


def _migrate_legacy_config_dir(session_id: str, target: Path) -> bool:
    """Copy a validated pre-hash config directory into the confined hash path."""
    validate_session_id(session_id)
    root = _CONFIG_ROOT.resolve()
    legacy = (_CONFIG_ROOT / session_id).resolve()
    if not legacy.is_relative_to(root) or not (legacy / "session-store.db").is_file():
        return False
    for item in legacy.rglob("*"):
        if item.is_symlink():
            raise ValueError("Legacy Copilot session directory contains a symlink")

    _CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=_CONFIG_ROOT, prefix=f"{session_storage_key(session_id)}-migrate-"
    ) as staging_root:
        staged = Path(staging_root) / "config"
        shutil.copytree(legacy, staged)
        if not (staged / "session-store.db").is_file():
            raise FileNotFoundError("Migrated legacy session has no session-store.db")
        if target.exists():
            shutil.rmtree(target)
        staged.replace(target)
    return True


def _elicitations(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    markers = state.get("elicitations")
    if markers is None:
        markers = {}
        legacy = state.get("pending_elicitation")
        if isinstance(legacy, dict) and legacy.get("elicitation_id"):
            markers[str(legacy["elicitation_id"])] = dict(legacy)
        state["elicitations"] = markers
    if not isinstance(markers, dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in markers.items()
    ):
        raise ValueError("Durable elicitation state is corrupt")
    return markers


def _sync_pending_elicitation(state: dict[str, Any]) -> None:
    markers = _elicitations(state)
    latest_id = next(reversed(markers), None)
    state["pending_elicitation"] = markers.get(latest_id) if latest_id else None


def _confirm_submitted_elicitations(state: dict[str, Any]) -> None:
    markers = _elicitations(state)
    for elicitation_id in [
        key for key, marker in markers.items() if marker.get("delivery") == "submitted"
    ]:
        del markers[elicitation_id]
    _sync_pending_elicitation(state)


async def _get_legacy_state_item(session_id: str) -> Any:
    legacy_state_store = FoundryStateStore(_legacy_session_state_store_name(session_id))
    try:
        try:
            return await legacy_state_store.get_item("state")
        except FoundryStorageNotFoundError:
            return None
    finally:
        await legacy_state_store.aclose()


@dataclass
class _HarnessSlot:
    ready: asyncio.Future[CopilotHarness]
    closing: bool = False


_HARNESS_SLOTS: dict[str, _HarnessSlot] = {}
_CLIENT_CANCEL_REQUESTED: set[str] = set()


async def get_invocation_status(invocation_id: str) -> dict[str, Any] | None:
    """Return one invocation's durable polling record."""
    return await _INVOCATION_STORE.get(invocation_id)


def reserve_harness(session_id: str) -> _HarnessSlot:
    """Reserve startup routing before ``task.start()`` returns to the caller."""
    validate_session_id(session_id)
    current = _HARNESS_SLOTS.get(session_id)
    if current is not None and not current.closing:
        return current
    slot = _HarnessSlot(asyncio.get_running_loop().create_future())
    _HARNESS_SLOTS[session_id] = slot
    return slot


def fail_harness_start(
    session_id: str,
    exc: BaseException,
    expected_slot: _HarnessSlot | None = None,
) -> None:
    """Unblock rapid follow-ups when starting the durable task failed."""
    slot = _HARNESS_SLOTS.get(session_id)
    if slot is None or (expected_slot is not None and slot is not expected_slot):
        return
    slot.closing = True
    if not slot.ready.done():
        slot.ready.set_exception(exc)
        slot.ready.exception()
    _HARNESS_SLOTS.pop(session_id, None)


async def _ready_harness(session_id: str) -> CopilotHarness | None:
    slot = _HARNESS_SLOTS.get(session_id)
    if slot is None or slot.closing:
        return None
    try:
        harness = await asyncio.wait_for(
            asyncio.shield(slot.ready), _READY_TIMEOUT_SECONDS
        )
    except (TimeoutError, HarnessClosingError):
        return None
    if slot.closing:
        return None
    return harness


async def submit_native_input(
    session_id: str, input_id: str, prompt: str, mode: str
) -> dict[str, Any] | None:
    """Route a follow-up through the active task consumer, if one is usable."""
    validate_session_id(session_id)
    harness = await _ready_harness(session_id)
    if harness is None:
        return None
    try:
        return await harness.queue_input(input_id, prompt, mode)
    except HarnessClosingError:
        return None


async def submit_elicitation_decision(
    session_id: str,
    elicitation_id: str,
    action: str,
    content: dict | None,
) -> dict[str, Any] | None:
    """Route an HITL answer through the active task's durable control queue."""
    validate_session_id(session_id)
    harness = await _ready_harness(session_id)
    if harness is None:
        return None
    try:
        return await harness.queue_elicitation_decision(elicitation_id, action, content)
    except HarnessClosingError:
        return None


def mark_client_cancel(session_id: str) -> None:
    """Record an explicit HTTP cancellation independently of framework flags."""
    validate_session_id(session_id)
    _CLIENT_CANCEL_REQUESTED.add(session_id)


def _consume_client_cancel(session_id: str) -> bool:
    if session_id in _CLIENT_CANCEL_REQUESTED:
        _CLIENT_CANCEL_REQUESTED.remove(session_id)
        return True
    return False


def _event_payload(event: Any) -> dict:
    """Render a Copilot SessionEvent as a stream payload."""
    try:
        body = event.to_dict()
    except Exception:  # pylint: disable=broad-except
        body = {"type": str(getattr(event, "type", "unknown"))}
    return {"kind": "copilot_event", **body}


def _input_journal(state: dict[str, Any]) -> list[dict[str, Any]]:
    journal = state.setdefault("input_journal", [])
    if not isinstance(journal, list):
        raise ValueError("Durable input journal is corrupt")
    return journal


def _decision_message(elicitation_id: str, action: str, content: dict | None) -> str:
    payload: dict[str, Any] = {
        "elicitation_id": elicitation_id,
        "action": action,
    }
    if content is not None:
        payload["content"] = content
    return f"[human elicitation response] {json.dumps(payload, sort_keys=True)}"


def _same_elicitation_decision(
    existing: dict[str, Any], requested: dict[str, Any]
) -> bool:
    """Compare decisions using canonical JSON so bools remain distinct from numbers."""
    return json.dumps(
        existing,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) == json.dumps(
        requested,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@multi_turn_task(name="copilot_agent", steerable=True)
async def copilot_agent(ctx: TaskContext[dict]) -> None:
    """Supervise one Copilot turn and durably serialize native controls."""
    session_id = validate_session_id(str(ctx.input["session_id"]))
    inv_id: str = ctx.input["invocation_id"]
    prompt: str = ctx.input["prompt"]
    recovered = ctx.entry_mode == "recovered"
    task_id = f"copilot-{session_id}"
    framework_input_id = str(ctx.input_id)
    config_dir = _config_dir_for(session_id)
    slot = reserve_harness(session_id)
    harness = CopilotHarness()
    stream = None
    state_store = None
    watcher: asyncio.Task[None] | None = None
    seq = 0

    try:
        if not (config_dir / "session-store.db").exists():
            await asyncio.to_thread(_migrate_legacy_config_dir, session_id, config_dir)
        state_store = await FoundryStateStore.get_or_create(
            session_state_store_name(session_id),
            item_ttl_seconds=30 * 24 * 60 * 60,
            description="Copilot durable controls and snapshot marker",
        )
        state_item = await state_store.get_item("state")
        legacy_state_migrated = False
        if state_item is None:
            state_item = await _get_legacy_state_item(session_id)
            legacy_state_migrated = state_item is not None
        state: dict[str, Any] = (
            dict(state_item.value)
            if state_item is not None and isinstance(state_item.value, dict)
            else {}
        )
        _elicitations(state)
        _sync_pending_elicitation(state)
        if legacy_state_migrated:
            await state_store.set_item("state", state)

        incoming_input_id = ctx.input.get("input_id")
        incoming_mode = ctx.input.get("mode") or "enqueue"
        if incoming_input_id is not None:
            journal = _input_journal(state)
            incoming_record = next(
                (
                    record
                    for record in journal
                    if record.get("input_id") == incoming_input_id
                ),
                None,
            )
            if incoming_record is not None and (
                incoming_record.get("prompt") != prompt
                or incoming_record.get("mode") != incoming_mode
            ):
                raise ValueError(
                    "input_id is already bound to a different prompt or mode"
                )
            if incoming_record is None:
                unfinished = [
                    record for record in journal if record.get("status") != "covered"
                ]
                if len(unfinished) >= _MAX_INPUT_JOURNAL_ENTRIES:
                    raise RuntimeError(
                        "Durable native-input journal is full; wait for the "
                        "current Copilot turn to reach idle before retrying."
                    )
                incoming_record = {
                    "input_id": incoming_input_id,
                    "prompt": prompt,
                    "mode": incoming_mode,
                    "status": "accepted",
                }
                journal.append(incoming_record)
                journal_size = len(
                    json.dumps(journal, separators=(",", ":")).encode("utf-8")
                )
                if journal_size > _MAX_INPUT_JOURNAL_BYTES:
                    journal.pop()
                    raise ValueError(
                        "Durable native-input journal would exceed 512 KiB; "
                        "send a smaller input or wait for the current turn to "
                        "reach idle."
                    )
                await state_store.set_item("state", state)
        await _INVOCATION_STORE.put(
            inv_id,
            task_id=task_id,
            framework_input_id=framework_input_id,
            status="running",
            task_status="in_progress",
        )

        stream = await streams.get_or_create(inv_id)
        seq = await stream.last_cursor() or 0

        async def emit(payload: dict[str, Any]) -> None:
            nonlocal seq
            seq += 1
            await stream.emit({"sequence_number": seq, **payload})

        async def persist_state() -> None:
            await state_store.set_item("state", state)

        async def save_snapshot(*, live: bool) -> None:
            await _SNAPSHOT_STORE.save(session_id, config_dir, live=live)
            state["has_snapshot"] = True
            await persist_state()

        def snapshot_ready() -> bool:
            return (config_dir / "session-store.db").is_file() and (
                config_dir / "session-state" / session_id / "session.db"
            ).is_file()

        async def persist_input_delivery(record: dict[str, Any]) -> None:
            if state.get("has_snapshot") or snapshot_ready():
                await save_snapshot(live=True)
            else:
                logger.info(
                    "copilot_input_delivered_before_snapshot_ready "
                    "session=%s input_id=%s",
                    session_id,
                    record["input_id"],
                )
            record["status"] = "delivered"
            record["receipt"] = {
                "status": "delivered",
                "input_id": record["input_id"],
            }
            await persist_state()

        async def process_elicitation_request(request: ElicitationRequest) -> None:
            try:
                markers = _elicitations(state)
                existing = markers.get(request.elicitation_id, {})
                markers[request.elicitation_id] = {
                    "elicitation_id": request.elicitation_id,
                    "message": request.message,
                    "schema": request.schema,
                    "decision": existing.get("decision"),
                    "delivery": existing.get("delivery"),
                }
                _sync_pending_elicitation(state)
                await persist_state()
                await emit(
                    {
                        "type": "elicitation_request",
                        "elicitation_id": request.elicitation_id,
                        "message": request.message,
                        "schema": request.schema,
                    }
                )
            except BaseException as exc:
                if not request.acknowledged.done():
                    request.acknowledged.set_exception(exc)
                raise
            else:
                if not request.acknowledged.done():
                    request.acknowledged.set_result(None)

        async def process_native_input(request: NativeInputRequest) -> None:
            try:
                journal = _input_journal(state)
                record = next(
                    (
                        entry
                        for entry in journal
                        if entry.get("input_id") == request.input_id
                    ),
                    None,
                )
                if record is not None and (
                    record.get("prompt") != request.prompt
                    or record.get("mode") != request.mode
                ):
                    error = ValueError(
                        "input_id is already bound to a different prompt or mode"
                    )
                    if not request.acknowledged.done():
                        request.acknowledged.set_exception(error)
                    return
                if record is not None and record.get("status") == "delivered":
                    receipt = record.get("receipt")
                    if not isinstance(receipt, dict):
                        receipt = {
                            "status": "delivered",
                            "input_id": request.input_id,
                        }
                    result = {**receipt, "deduplicated": True}
                else:
                    if record is None:
                        unfinished = [
                            entry
                            for entry in journal
                            if entry.get("status") != "covered"
                        ]
                        if len(unfinished) >= _MAX_INPUT_JOURNAL_ENTRIES:
                            error = RuntimeError(
                                "Durable native-input journal is full; wait for the "
                                "current Copilot turn to reach idle before retrying."
                            )
                            if not request.acknowledged.done():
                                request.acknowledged.set_exception(error)
                            return
                        record = {
                            "input_id": request.input_id,
                            "prompt": request.prompt,
                            "mode": request.mode,
                            "status": "accepted",
                        }
                        journal.append(record)
                        journal_size = len(
                            json.dumps(journal, separators=(",", ":")).encode("utf-8")
                        )
                        if journal_size > _MAX_INPUT_JOURNAL_BYTES:
                            journal.pop()
                            error = ValueError(
                                "Durable native-input journal would exceed 512 KiB; "
                                "send a smaller input or wait for the current turn "
                                "to reach idle."
                            )
                            if not request.acknowledged.done():
                                request.acknowledged.set_exception(error)
                            return
                        await persist_state()
                    await harness.send(
                        record["prompt"],
                        mode=record["mode"],
                        causal_idle=True,
                    )
                    await persist_input_delivery(record)
                    result = {
                        **record["receipt"],
                        "deduplicated": False,
                    }
                if not request.acknowledged.done():
                    request.acknowledged.set_result(result)
            except BaseException as exc:
                if not request.acknowledged.done():
                    request.acknowledged.set_exception(exc)
                raise

        async def deliver_elicitation_decision(
            elicitation_id: str, action: str, content: dict | None
        ) -> str:
            live = harness.answer_elicitation(elicitation_id, action, content)
            if live:
                delivery = "answered"
            else:
                await harness.send(
                    _decision_message(elicitation_id, action, content),
                    mode="enqueue",
                    causal_idle=True,
                )
                delivery = "delivered_as_message"
            harness.discard_recovered_elicitation(elicitation_id)
            await save_snapshot(live=True)
            marker = _elicitations(state).get(elicitation_id)
            if (
                marker is not None
                and (marker.get("decision") or {}).get("action") == action
            ):
                marker["delivery"] = "submitted"
            _sync_pending_elicitation(state)
            await persist_state()
            return delivery

        async def process_elicitation(
            request: ElicitationDecisionRequest,
        ) -> None:
            try:
                marker = _elicitations(state).get(request.elicitation_id)
                if marker is None:
                    error = ValueError(
                        "elicitation_id does not match the pending request"
                    )
                    if not request.acknowledged.done():
                        request.acknowledged.set_exception(error)
                    return
                requested_decision = {
                    "action": request.action,
                    "content": request.content,
                }
                existing_decision = marker.get("decision")
                if existing_decision is not None:
                    if not _same_elicitation_decision(
                        existing_decision, requested_decision
                    ):
                        error = ValueError(
                            "elicitation decision is already bound to different "
                            "action or content"
                        )
                        if not request.acknowledged.done():
                            request.acknowledged.set_exception(error)
                        return
                    if marker.get("delivery") == "submitted":
                        receipt = marker.get("receipt")
                        if not isinstance(receipt, dict):
                            receipt = {
                                "status": "answered",
                                "elicitation_id": request.elicitation_id,
                            }
                        if not request.acknowledged.done():
                            request.acknowledged.set_result(dict(receipt))
                        return
                marker["decision"] = requested_decision
                marker["delivery"] = "accepted"
                _sync_pending_elicitation(state)
                await persist_state()
                delivery = await deliver_elicitation_decision(
                    request.elicitation_id, request.action, request.content
                )
                receipt = {
                    "status": delivery,
                    "elicitation_id": request.elicitation_id,
                }
                marker["receipt"] = receipt
                await persist_state()
                if not request.acknowledged.done():
                    request.acknowledged.set_result(dict(receipt))
            except BaseException as exc:
                if not request.acknowledged.done():
                    request.acknowledged.set_exception(exc)
                raise

        await emit(
            {
                "type": "turn_start",
                "session_id": session_id,
                "entry_mode": ctx.entry_mode,
                "recovery_count": ctx.recovery_count,
            }
        )

        have_session = (config_dir / "session-store.db").exists()
        if not have_session:
            restored = await _SNAPSHOT_STORE.restore(session_id, config_dir)
            if state.get("has_snapshot") and not restored:
                raise FileNotFoundError(
                    "Durable state says a Copilot snapshot exists, but it could "
                    "not be restored. Refusing to create a new conversation."
                )
            have_session = restored and (config_dir / "session-store.db").exists()
            if restored and not have_session:
                raise FileNotFoundError(
                    "Restored Copilot snapshot has no session-store.db"
                )

        elicitation_markers = list(_elicitations(state).values())
        harness.bind_recovered_elicitations(elicitation_markers)

        await harness.start(
            session_id,
            recover=have_session,
            config_directory=str(config_dir),
        )
        if not slot.ready.done():
            slot.ready.set_result(harness)

        if recovered:
            await emit({"type": "recovered", "recovery_count": ctx.recovery_count})
            for marker in elicitation_markers:
                if marker.get("decision"):
                    continue
                await emit(
                    {
                        "type": "elicitation_request",
                        "recovered": True,
                        **marker,
                    }
                )

        incoming_record = next(
            (
                record
                for record in _input_journal(state)
                if record.get("input_id") == incoming_input_id
            ),
            None,
        )
        if incoming_record is not None and (
            incoming_record.get("prompt") != prompt
            or incoming_record.get("mode") != incoming_mode
        ):
            raise ValueError("input_id is already bound to a different prompt or mode")
        if incoming_record is None:
            await harness.send(prompt, causal_idle=True)

        # Re-drive controls that were durably accepted but not covered by a
        # completed Copilot idle boundary. A crash after send and before the
        # receipt update can therefore deliver at least twice.
        for record in list(_input_journal(state)):
            if record.get("status") in {"accepted", "delivered"}:
                await harness.send(
                    record["prompt"],
                    mode=record["mode"],
                    causal_idle=True,
                )
                await persist_input_delivery(record)

        for marker in list(_elicitations(state).values()):
            decision = marker.get("decision")
            if not decision:
                continue
            await deliver_elicitation_decision(
                marker["elicitation_id"],
                decision["action"],
                decision.get("content"),
            )

        async def watch_stop() -> None:
            cancel_wait = asyncio.create_task(ctx.cancel.wait())
            shutdown_wait = asyncio.create_task(ctx.shutdown.wait())
            try:
                await asyncio.wait(
                    {cancel_wait, shutdown_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                await harness.abort()
            finally:
                for child in (cancel_wait, shutdown_wait):
                    if not child.done():
                        child.cancel()
                await asyncio.gather(cancel_wait, shutdown_wait, return_exceptions=True)

        watcher = asyncio.create_task(watch_stop())
        async for event in harness.events():
            if ctx.cancel.is_set() or ctx.shutdown.is_set():
                break
            if isinstance(event, TodoCheckpointRequest):
                try:
                    await save_snapshot(live=True)
                    state["todo_fingerprint"] = event.fingerprint
                    await persist_state()
                    await emit(
                        {
                            "type": "todo_checkpoint",
                            "fingerprint": event.fingerprint,
                        }
                    )
                except BaseException as exc:
                    if not event.acknowledged.done():
                        event.acknowledged.set_exception(exc)
                    raise
                else:
                    if not event.acknowledged.done():
                        event.acknowledged.set_result(None)
                continue
            if isinstance(event, TodoCheckpointDetectionFailure):
                if not event.acknowledged.done():
                    event.acknowledged.set_exception(event.error)
                raise event.error
            if isinstance(event, ElicitationRequest):
                await process_elicitation_request(event)
                continue
            if isinstance(event, NativeInputRequest):
                await process_native_input(event)
                continue
            if isinstance(event, ElicitationDecisionRequest):
                await process_elicitation(event)
                continue
            await emit(_event_payload(event))
            _maybe_crash(seq, enabled=not recovered)

        explicit_cancel = _consume_client_cancel(session_id) or bool(
            getattr(ctx, "cancel_requested", False)
        )
        shutting_down = ctx.shutdown.is_set() and not explicit_cancel
        cancelled = ctx.cancel.is_set() and not shutting_down

        slot.closing = True
        harness.stop_accepting_controls()
        await harness.abort()
        await harness.close()
        await save_snapshot(live=True)

        if shutting_down:
            return await ctx.exit_for_recovery()

        if cancelled:
            state["input_journal"] = []
            state["elicitations"] = {}
            state["pending_elicitation"] = None
            await persist_state()
            await _INVOCATION_STORE.put(
                inv_id,
                task_id=task_id,
                framework_input_id=framework_input_id,
                status="cancelled",
                task_status="cancelled",
            )
            await emit({"type": "cancelled"})
            await stream.close()
            return

        journal = _input_journal(state)
        for record in journal:
            if record.get("status") == "delivered":
                record["status"] = "covered"
        state["input_journal"] = [
            record for record in journal if record.get("status") != "covered"
        ]
        _confirm_submitted_elicitations(state)
        await persist_state()
        await _INVOCATION_STORE.put(
            inv_id,
            task_id=task_id,
            framework_input_id=framework_input_id,
            status="completed",
            task_status="suspended",
        )
        await emit({"type": "turn_complete"})
        await stream.close()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("copilot_agent turn failed; emitting terminal frame")
        try:
            await _INVOCATION_STORE.put(
                inv_id,
                task_id=task_id,
                framework_input_id=framework_input_id,
                status="failed",
                task_status="failed",
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("failed to persist invocation failure status")
        if not slot.ready.done():
            slot.ready.set_exception(exc)
            slot.ready.exception()
        if stream is not None:
            try:
                seq += 1
                await stream.emit(
                    {
                        "sequence_number": seq,
                        "type": "turn_failed",
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc)[:2000],
                        },
                    }
                )
            except Exception:  # pylint: disable=broad-except
                logger.exception("failed to emit terminal turn_failed frame")
            try:
                await stream.close()
            except Exception:  # pylint: disable=broad-except
                logger.exception("failed to close failed turn stream")
        raise
    finally:
        slot.closing = True
        if not slot.ready.done():
            slot.ready.set_exception(
                HarnessClosingError("Copilot harness closed before becoming ready")
            )
            slot.ready.exception()
        harness.stop_accepting_controls()
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        await harness.close()
        if state_store is not None:
            try:
                await state_store.aclose()
            except Exception:  # pylint: disable=broad-except
                logger.exception("failed to close Copilot state store")
        if _HARNESS_SLOTS.get(session_id) is slot:
            _HARNESS_SLOTS.pop(session_id, None)
        _CLIENT_CANCEL_REQUESTED.discard(session_id)


def _maybe_crash(emitted: int, *, enabled: bool = True) -> None:
    """Hard-crash after N emitted events when the one-shot hook is armed."""
    if enabled and 0 <= _SIMULATE_CRASH_AFTER_EVENTS <= emitted:
        logger.warning(
            "SIMULATE_CRASH_AFTER_EVENTS=%d reached (emitted=%d); os._exit(1).",
            _SIMULATE_CRASH_AFTER_EVENTS,
            emitted,
        )
        os._exit(1)
