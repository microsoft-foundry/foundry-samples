# Copyright (c) Microsoft. All rights reserved.

"""Wire-level tests for the LangChain Python Voice Live Bridge sample."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    ResponseOutputTextDelta,
    new_item_id,
)
from starlette.testclient import TestClient

from main import create_app as create_entry_app
from response_coordinator import ResponseCoordinator
from scripts.smoke_test import ResponseValidator
from state import (
    MAX_ACTIVE_RESPONSES,
    MAX_PENDING_PROACTIVE,
    MAX_SEEN_INPUTS,
    MAX_TERMINAL_SENDS,
    MAX_TRACKED_PLAYBACK_RESPONSES,
    InputClaim,
    OperationOutcome,
    SessionState,
)
from voice_runtime import IDLE_REMINDER_TEXT, VoiceRuntime, create_app


@dataclass(slots=True)
class BlockingScript:
    first_chunk: str
    started: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)


def block_next_output(app: Any, blocked: BlockingScript) -> None:
    """Keep one echo response in flight for the cancellation tests."""
    coordinator = app.state.voice_runtime._coordinator
    send_fixed_output = coordinator._send_output

    async def send_output(operation: Any, text: str, streaming: bool, voice: Any) -> None:
        if blocked.started.is_set():
            await send_fixed_output(operation, text, streaming, voice)
            return
        blocked.started.set()
        try:
            await operation.session.send(
                ResponseOutputTextDelta(
                    response_id=operation.response_id,
                    item_id=new_item_id(),
                    delta=blocked.first_chunk,
                )
            )
            await asyncio.Future()
        except asyncio.CancelledError:
            blocked.cancelled.set()
            raise

    coordinator._send_output = send_output


class RecordingSession:
    def __init__(self, state: SessionState | None = None) -> None:
        self.state = state
        self.sent: list[Any] = []
        self.capacity_at_done: int | None = None

    async def send(self, event: Any) -> None:
        self.sent.append(event)
        if event.__class__.__name__ == "ResponseDone" and self.state is not None:
            self.capacity_at_done = self.state.active_response_count


def frame(message_type: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": message_type,
        "id": f"m_{uuid.uuid4().hex}",
        "ts": "2026-08-31T00:00:00Z",
        **fields,
    }


def start(websocket: Any, protocol: str = "1.0") -> dict[str, Any]:
    websocket.send_json(
        frame(
            "session.start",
            protocol_version=protocol,
            reconnect=False,
            response_timeouts={
                "first_output_ms": 30_000,
                "idle_ms": 30_000,
                "max_duration_ms": 120_000,
            },
        )
    )
    return websocket.receive_json()


def send_user(websocket: Any, item_id: str, text: str) -> None:
    websocket.send_json(
        frame(
            "user.message",
            item_id=item_id,
            content=[{"type": "input_text", "text": text}],
        )
    )


def receive_until(websocket: Any, terminal: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    while not frames or frames[-1]["type"] != terminal:
        frames.append(websocket.receive_json())
    return frames


def receive_type(websocket: Any, expected: str) -> dict[str, Any]:
    while True:
        received = websocket.receive_json()
        if received["type"] == expected:
            return received


@pytest.mark.parametrize("second_text", ["", "second"])
def test_input_resolutions_preserve_dispatch_order(second_text: str) -> None:
    app = create_app(configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_first", "first")
        send_user(ws, "in_second", second_text)
        resolved: list[str] = []
        terminals = 0
        while terminals < 2:
            event = ws.receive_json()
            assert event["type"] != "error"
            if event["type"] in {"response.created", "response.none"}:
                resolved.extend(event["in_reply_to"])
            if event["type"] in {"response.done", "response.none"}:
                terminals += 1
        assert resolved == ["in_first", "in_second"]


EXPECTED_STORY = (
    "Once a little rabbit found a lonely star. She carried it up the tallest hill, "
    "where friendly fireflies helped it shine again. "
    "That night, everyone dreamed of kindness and adventure."
)

def assert_story_response(received: list[dict[str, Any]]) -> None:
    assert [item["type"] for item in received] == [
        "response.created",
        *(["response.output_text.delta"] * 30),
        "response.output_text.done",
        "response.done",
    ]
    deltas = received[1:-2]
    assert len(EXPECTED_STORY.split()) == 30
    assert all(len(item["delta"].split()) == 1 for item in deltas)
    assert "".join(item["delta"] for item in deltas) == received[-2]["text"] == EXPECTED_STORY
    assert all(item["response_id"] == received[0]["response_id"] for item in received[1:])
    assert all(item["item_id"] == received[-2]["item_id"] for item in deltas)


def test_streams_thirty_word_story() -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_1", "First question")
        first = receive_until(ws, "response.done")
        assert_story_response(first)
        assert first[0]["in_reply_to"] == ["in_1"]

        send_user(ws, "in_2", "  你好 👋\n")
        second = receive_until(ws, "response.done")
        assert_story_response(second)
        assert second[0]["response_id"] != first[0]["response_id"]



@pytest.mark.parametrize("route", ["/voice_conversation_engine", "/invocations_ws"])
def test_entry_point_runs_echo_without_model_configuration(monkeypatch: Any, route: str) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    app = create_entry_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect(route) as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_1", "Hello")
        assert_story_response(receive_until(ws, "response.done"))


@pytest.mark.parametrize(
    "text",
    [
        "/stream hello",
        "/done hello",
        "/voice hello",
        "/none",
        "/proactive hello",
        "/cancel hello",
        "/error",
        "/session-error",
        "/end",
        "/end-now",
        "/help",
    ],
)
def test_slash_prefixed_text_triggers_story_without_commands(text: str) -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_1", text)
        received = receive_until(ws, "response.done")
        assert_story_response(received)
        assert received[-2].get("voice") is None



def test_protocol_mismatch_is_rejected() -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        rejected = start(ws, protocol="2.0")
        assert rejected["type"] == "session.rejected"
        assert rejected["code"] == "protocol_mismatch"
        send_user(ws, "in_after_rejection", "must not run")



def test_input_before_session_start_is_ignored() -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        send_user(ws, "in_before_start", "must not run")



def test_barge_in_cancels_echo_output() -> None:
    blocked = BlockingScript("unplayed")
    app = create_app(configure_observability=None)
    block_next_output(app, blocked)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_1", "Tell me a story")
        created = receive_type(ws, "response.created")
        receive_type(ws, "response.output_text.delta")
        ws.send_json(
            frame(
                "user.barge_in",
                response_id=created["response_id"],
                heard_text="The part heard.",
            )
        )
        assert blocked.cancelled.wait(2)

        send_user(ws, "in_2", "Continue")
        assert_story_response(receive_until(ws, "response.done"))


def test_no_input_reminder_and_end_call() -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        ws.send_json(frame("user.no_input", item_id="in_idle_1", count=1))
        reminder = receive_until(ws, "response.done")
        assert reminder[-2]["text"] == IDLE_REMINDER_TEXT

        ws.send_json(frame("user.no_input", item_id="in_idle_3", count=3))
        end = receive_type(ws, "end_call")
        assert end["mode"] == "drain"


@pytest.mark.asyncio
async def test_runtime_close_is_idempotent() -> None:
    runtime = VoiceRuntime()

    await runtime.close()
    await runtime.close()

    assert runtime._closed
    assert runtime._store.drain() == ()


def test_input_after_session_end_is_ignored() -> None:
    app = create_app(configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        ws.send_json(frame("session.end", reason="caller_hangup"))
        send_user(ws, "in_after_end", "must not run")



@pytest.mark.asyncio
async def test_async_source_sends_first_chunk_before_remainder_is_available() -> None:
    state = active_state()
    session = RecordingSession()
    coordinator = ResponseCoordinator()
    waiting = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    async def source() -> AsyncIterator[str]:
        try:
            yield "first"
            waiting.set()
            await release.wait()
            yield " second"
        finally:
            closed.set()

    assert coordinator.send_echo(session, state, "in_async", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        deltas = [
            event.delta for event in session.sent if event.type == "response.output_text.delta"
        ]
        assert deltas == ["first"]
        assert not any(event.type == "response.done" for event in session.sent)
        assert operation.task is not None and not operation.task.done()
        release.set()
        await asyncio.wait_for(operation.task, timeout=2)
        assert session.sent[-2].text == "first second"
        assert closed.is_set()
    finally:
        await coordinator.terminate_state(state, OperationOutcome.CANCELLED)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["timeout", "end_call", "source_error", "send_error"])
async def test_async_source_cleanup_on_cancellation_and_failure(action: str) -> None:
    state = active_state()
    waiting = asyncio.Event()
    closed = asyncio.Event()
    coordinator = ResponseCoordinator()

    class SessionWithSendFailure(RecordingSession):
        async def send(self, event: Any) -> None:
            if action == "send_error" and event.type == "response.output_text.delta":
                raise RuntimeError("test send failure")
            await super().send(event)

    session = SessionWithSendFailure()

    async def source() -> AsyncIterator[str]:
        try:
            yield "first"
            waiting.set()
            if action == "source_error":
                raise RuntimeError("test source failure")
            await asyncio.Future()
        finally:
            closed.set()

    assert coordinator.send_echo(session, state, "in_async", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    try:
        if action in {"timeout", "end_call"}:
            await asyncio.wait_for(waiting.wait(), timeout=2)
            if action == "timeout":
                coordinator.response_timeout(state, None, ["in_async"])
            else:
                await coordinator.terminate_state(state, OperationOutcome.END_CALL)
        assert operation.task is not None
        await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), timeout=2)
        await asyncio.sleep(0)
        assert closed.is_set()
        assert state.responses == {}
        assert state.input_responses == {}
        assert operation.outcome is (
            OperationOutcome.TIMEOUT if action == "timeout"
            else OperationOutcome.END_CALL if action == "end_call"
            else OperationOutcome.ERROR
        )
        assert not any(event.type == "response.done" for event in session.sent)
        if action in {"source_error", "send_error"}:
            assert session.sent[-1].type == "error"
    finally:
        await coordinator.terminate_state(state, OperationOutcome.CANCELLED)


def active_state() -> SessionState:
    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    return state


def test_input_ids_remain_deduplicated_and_bounded_for_connection() -> None:
    state = active_state()

    for index in range(MAX_SEEN_INPUTS):
        assert state.claim_input(f"in_{index}") is InputClaim.CLAIMED

    assert state.claim_input("in_0") is InputClaim.DUPLICATE
    assert state.claim_input("in_overflow") is InputClaim.CAPACITY_EXCEEDED


def test_response_and_proactive_capacity_are_bounded() -> None:
    state = active_state()
    coordinator = ResponseCoordinator()
    for index in range(MAX_ACTIVE_RESPONSES):
        state.responses[str(index)] = SimpleNamespace(capacity_released=False)
    assert not state.can_start_response()
    state.responses["0"].capacity_released = True
    assert state.can_start_response()
    for operation in state.responses.values():
        operation.capacity_released = True
    assert len(state.responses) == MAX_TERMINAL_SENDS
    assert not state.can_start_response()

    for index in range(MAX_PENDING_PROACTIVE):
        assert coordinator.reserve_proactive(state, f"proactive {index}") is not None
    assert coordinator.reserve_proactive(state, "overflow") is None


@pytest.mark.asyncio
async def test_terminating_state_cannot_send_reserved_proactive_admission() -> None:
    state = active_state()
    coordinator = ResponseCoordinator()
    response_id = coordinator.reserve_proactive(state, "hello")
    assert response_id is not None
    state.terminating = True
    session = RecordingSession()

    assert not await coordinator.send_proactive_request(session, state, response_id)  # type: ignore[arg-type]
    assert session.sent == []
    assert state.proactive_requests == {}


@pytest.mark.asyncio
async def test_response_releases_capacity_before_response_done_is_observable() -> None:
    state = active_state()
    session = RecordingSession(state)
    coordinator = ResponseCoordinator()

    assert coordinator.start_response(
        session,  # type: ignore[arg-type]
        state,
        "in_1",
        text="complete",
        streaming=False,
        voice=None,
    )
    operation = next(iter(state.responses.values()))
    assert operation.task is not None
    await operation.task

    assert session.capacity_at_done == 0


def test_third_no_input_cancels_active_work_before_end_call() -> None:
    blocked = BlockingScript("partial")
    app = create_app(configure_observability=None)
    block_next_output(app, blocked)

    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_blocked", "Start work")
        receive_type(ws, "response.output_text.delta")
        ws.send_json(frame("user.no_input", item_id="in_idle_3", count=3))
        assert receive_type(ws, "end_call")["mode"] == "drain"
        assert blocked.cancelled.is_set()


class BlockingOutputSession(RecordingSession):
    def __init__(self, blocked_type: str = "response.output_text.done") -> None:
        super().__init__()
        self.blocked_type = blocked_type
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def send(self, event: Any) -> None:
        if event.type == self.blocked_type:
            if event.type == "response.output_text.delta" and not any(
                item.type == "response.output_text.delta" for item in self.sent
            ):
                await super().send(event)
                return
            self.started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        await super().send(event)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "outcome"),
    [
        ("user_barge_in", "cancelled"),
        ("response_cancelled", "cancelled"),
        ("response_timeout", "timeout"),
        ("input_timeout", "timeout"),
        ("session_end", "end_call"),
        ("disconnect", "transport_error"),
        ("close", "cancelled"),
    ],
)
@pytest.mark.parametrize(
    "blocked_type", ["response.output_text.delta", "response.output_text.done", "response.done"]
)
async def test_control_events_cancel_pending_echo_and_clear_correlations(
    action: str, outcome: str, blocked_type: str
) -> None:
    runtime = VoiceRuntime()
    session = BlockingOutputSession(blocked_type)
    await runtime.on_session_start(session, SimpleNamespace(protocol_version="1.0"))
    await runtime.on_user_message(
        session,
        SimpleNamespace(item_id="in_blocked", content=[InputTextPart(text="echo")]),
    )
    await asyncio.wait_for(session.started.wait(), timeout=2)
    state = runtime._state_for(session)
    assert state is not None
    operation = next(iter(state.responses.values()))

    try:
        if blocked_type == "response.output_text.delta":
            assert [event.delta for event in session.sent if event.type == blocked_type] == ["Once"]
        if action in {"user_barge_in", "response_cancelled", "response_timeout"}:
            await getattr(runtime, f"on_{action}")(
                session,
                SimpleNamespace(
                    response_id=operation.response_id, heard_text="heard", item_ids=[]
                ),
            )
        elif action == "input_timeout":
            await runtime.on_response_timeout(
                session, SimpleNamespace(response_id=None, item_ids=["in_blocked"])
            )
        elif action == "session_end":
            await runtime.on_session_end(session, SimpleNamespace())
        elif action == "disconnect":
            runtime.on_connection_terminating(session)
        else:
            await runtime.close()

        await asyncio.wait_for(session.cancelled.wait(), timeout=2)
        assert operation.task is not None
        await asyncio.gather(operation.task, return_exceptions=True)
        await asyncio.sleep(0)  # Let the registered task-finalization callbacks run.
        assert operation.outcome is not None
        assert operation.outcome.value == outcome
        assert state.responses == {}
        assert state.input_responses == {}
        assert not any(event.type == "response.done" for event in session.sent)
        if action in {"user_barge_in", "response_cancelled"}:
            assert state.heard_text_by_response[operation.response_id] == "heard"
    finally:
        await runtime.close()
    assert state.heard_text_by_response == {}


@pytest.mark.parametrize("event_type", ["user.barge_in", "response.cancelled"])
def test_late_playback_event_synchronizes_heard_text(event_type: str) -> None:
    app = create_app(configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_first", "complete echo")
        first = receive_until(ws, "response.done")
        response_id = first[0]["response_id"]
        ws.send_json(frame(event_type, response_id=response_id, heard_text="complete"))
        send_user(ws, "in_next", "next")
        assert_story_response(receive_until(ws, "response.done"))
        state = next(iter(app.state.voice_runtime._store._states.values()))
        assert state.heard_text_by_response[response_id] == "complete"


def test_playback_state_is_bounded_and_ignores_unknown_responses() -> None:
    state = active_state()
    for index in range(MAX_TRACKED_PLAYBACK_RESPONSES + 1):
        state.track_response(f"r_{index}")
    state.record_heard_text("r_unknown", "must not be retained")
    state.record_heard_text(f"r_{MAX_TRACKED_PLAYBACK_RESPONSES}", "heard")
    assert len(state.heard_text_by_response) == MAX_TRACKED_PLAYBACK_RESPONSES
    assert "r_0" not in state.heard_text_by_response
    assert "r_unknown" not in state.heard_text_by_response
    assert state.heard_text_by_response[f"r_{MAX_TRACKED_PLAYBACK_RESPONSES}"] == "heard"


def test_smoke_validator_accepts_ordered_correlated_response() -> None:
    validator = ResponseValidator()
    assert not validator.consume({"type": "response.created", "response_id": "resp_1"})
    assert not validator.consume(
        {
            "type": "response.output_text.delta",
            "response_id": "resp_1",
            "item_id": "item_1",
            "delta": "hello",
        }
    )
    assert not validator.consume(
        {
            "type": "response.output_text.done",
            "response_id": "resp_1",
            "item_id": "item_1",
            "text": "hello",
        }
    )
    assert validator.consume({"type": "response.done", "response_id": "resp_1"})


@pytest.mark.parametrize(
    "frames",
    [
        [{"type": "response.done", "response_id": "resp_1"}],
        [{"type": "response.none"}],
        [
            {"type": "response.created", "response_id": "resp_1"},
            {"type": "response.done", "response_id": "resp_1"},
        ],
        [
            {"type": "response.created", "response_id": "resp_1"},
            {
                "type": "response.output_text.done",
                "response_id": "resp_2",
                "item_id": "item_1",
                "text": "hello",
            },
        ],
        [
            {"type": "response.created", "response_id": "resp_1"},
            {
                "type": "response.output_text.done",
                "response_id": "resp_1",
                "item_id": "item_1",
                "text": "",
            },
        ],
    ],
)
def test_smoke_validator_rejects_invalid_sequences(frames: list[dict[str, Any]]) -> None:
    validator = ResponseValidator()
    with pytest.raises(RuntimeError):
        for received in frames:
            validator.consume(received)
