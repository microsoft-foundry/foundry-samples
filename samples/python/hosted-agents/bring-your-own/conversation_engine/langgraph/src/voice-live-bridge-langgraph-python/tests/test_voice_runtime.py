# Copyright (c) Microsoft. All rights reserved.

"""Wire-level tests for the LangGraph Python Voice Live Bridge sample."""

from __future__ import annotations

import asyncio
import json
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
        state.responses[str(index)] = SimpleNamespace(capacity_released=False, decline_only=False)
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


class DeclineHostSocket:
    """Gate one outbound decline while the real SDK keeps receiving frames."""

    def __init__(self) -> None:
        self.scope: dict[str, Any] = {}
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames: list[dict[str, Any]] = []
        self.changed = asyncio.Event()
        self.none_started = asyncio.Event()
        self.release_none = asyncio.Event()

    def enqueue(self, kind: str, **fields: Any) -> None:
        self.incoming.put_nowait(
            {"type": "websocket.receive", "text": json.dumps(frame(kind, **fields))}
        )

    async def receive(self) -> dict[str, Any]:
        return await self.incoming.get()

    async def send_text(self, text: str) -> None:
        event = json.loads(text)
        if event["type"] == "response.none":
            self.none_started.set()
            await self.release_none.wait()
        self.frames.append(event)
        self.changed.set()


def _create_decline_app() -> Any:
    return create_app(configure_observability=None)


def _enqueue_decline_start(socket: DeclineHostSocket) -> None:
    socket.enqueue(
        "session.start",
        protocol_version="1.0",
        reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30000},
    )


async def _wait_for_decline_event(socket: DeclineHostSocket, condition: Any) -> None:
    async with asyncio.timeout(2):
        while not condition():
            socket.changed.clear()
            await socket.changed.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["response.timeout", "user.speech_started", "session.end"])
async def test_decline_backpressure_keeps_control_callbacks_responsive(kind: str) -> None:
    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    handled = asyncio.Event()
    callback = app._voice_callbacks[kind]

    async def observe(session: Any, event: Any) -> None:
        handled.set()
        await callback(session, event)

    app._voice_callbacks[kind] = observe
    _enqueue_decline_start(socket)
    socket.enqueue("user.message", item_id="in_empty", content=[{"type": "input_text", "text": ""}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(socket.none_started.wait(), 2)
        fields: dict[str, Any] = {}
        if kind == "response.timeout":
            fields = {"stage": "first_output", "item_ids": ["in_empty"]}
        elif kind == "session.end":
            fields = {"reason": "test_complete"}
        socket.enqueue(kind, **fields)
        await asyncio.wait_for(handled.wait(), 2)
        assert not socket.release_none.is_set()
    finally:
        socket.release_none.set()
        if not connection.done():
            socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.asyncio
async def test_cancelled_resolution_cannot_release_a_later_input_early() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    timeout_handled = asyncio.Event()
    callback = app._voice_callbacks["response.timeout"]

    async def observe(session: Any, event: Any) -> None:
        await callback(session, event)
        timeout_handled.set()

    app._voice_callbacks["response.timeout"] = observe
    _enqueue_decline_start(socket)
    for item_id, text in [("in_first", ""), ("in_cancel", "unused"), ("in_last", "last")]:
        socket.enqueue(
            "user.message", item_id=item_id, content=[{"type": "input_text", "text": text}]
        )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(socket.none_started.wait(), 2)
        socket.enqueue("response.timeout", stage="first_output", item_ids=["in_cancel"])
        await asyncio.wait_for(timeout_handled.wait(), 2)
        state = runtime._store.active(Session._current(socket))
        assert state is not None
        await asyncio.sleep(0)
        assert not any("in_reply_to" in event for event in socket.frames)
        socket.release_none.set()
        await _wait_for_decline_event(
            socket,
            lambda: any(event["type"] == "response.done" for event in socket.frames)
        )
        resolved = [item for event in socket.frames for item in event.get("in_reply_to", [])]
        assert resolved == ["in_first", "in_last"]
    finally:
        socket.release_none.set()
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_queued", [False, True])
async def test_pending_declines_are_bounded_and_drained(cancel_queued: bool) -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from state import MAX_PENDING_DECLINES

    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    session = Session._create(socket)
    await runtime.on_session_start(session, SimpleNamespace(protocol_version="1.0"))
    state = runtime._store.active(session)
    assert state is not None
    try:
        for index in range(MAX_PENDING_DECLINES):
            await runtime.on_user_message(
                session,
                SimpleNamespace(item_id=f"in_decline_{index}", content=[InputTextPart(text="")]),
            )
        if cancel_queued:
            await asyncio.wait_for(socket.none_started.wait(), 2)
            tasks = []
            for index in range(1, MAX_PENDING_DECLINES):
                operation = state.responses[state.input_responses[f"in_decline_{index}"]]
                tasks.append(operation.task)
                runtime._coordinator.response_timeout(state, None, [f"in_decline_{index}"])
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)
        assert state.pending_decline_count == MAX_PENDING_DECLINES
        assert state.active_response_count == 0
        with pytest.raises(RuntimeError, match="capacity exceeded"):
            await runtime.on_user_message(
                session,
                SimpleNamespace(item_id="in_overflow", content=[InputTextPart(text="")]),
            )
    finally:
        socket.release_none.set()
        await runtime.close()
    assert not state.responses
    assert not state.input_responses
    assert state.input_resolution_tail is not None
    await asyncio.wait_for(asyncio.shield(state.input_resolution_tail), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_event", ["barge_in", "cancelled", "timeout"])
@pytest.mark.parametrize("detached", [False, True])
async def test_repeated_cancellation_and_session_end_drain_async_cleanup(
    first_event: str, detached: bool
) -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    socket = DeclineHostSocket()
    session = Session._create(socket)
    coordinator = ResponseCoordinator()
    started = asyncio.Event()
    cleanup_entered = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def source():
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_entered.set()
            await release_cleanup.wait()
            cleanup_finished.set()

    assert coordinator.start_response(session, state, "in_cleanup", source())
    operation = next(iter(state.responses.values()))
    termination = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        if first_event == "barge_in":
            coordinator.barge_in(state, operation.response_id, "heard")
        elif first_event == "cancelled":
            coordinator.response_cancelled(state, operation.response_id, "heard")
        else:
            coordinator.response_timeout(state, None, ["in_cleanup"])
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        coordinator.response_cancelled(state, operation.response_id, "heard")
        coordinator.response_timeout(state, operation.response_id, None)
        assert state.active_response_count == 1
        assert state.input_responses["in_cleanup"] == operation.response_id
        if detached:
            coordinator.detach_terminating_state(state, OperationOutcome.TRANSPORT_ERROR)
            termination = asyncio.create_task(coordinator.wait_for_detached_tasks())
        else:
            termination = asyncio.create_task(
                coordinator.terminate_state(state, OperationOutcome.END_CALL)
            )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not termination.done()
        assert operation.task is not None
        assert operation.task.cancelling() == 1
        assert not cleanup_finished.is_set()
    finally:
        release_cleanup.set()
        if termination is not None:
            await asyncio.wait_for(termination, 2)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    assert cleanup_finished.is_set()
    assert not state.responses
    assert not state.input_responses
    assert operation.outcome is (
        OperationOutcome.TIMEOUT if first_event == "timeout" else OperationOutcome.CANCELLED
    )
    assert not any(event["type"] == "response.done" for event in socket.frames)


@pytest.mark.asyncio
async def test_cancel_before_task_start_releases_correlations_without_running_source() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    socket = DeclineHostSocket()
    coordinator = ResponseCoordinator()
    source_started = False

    async def source():
        nonlocal source_started
        source_started = True
        yield "must not run"

    assert coordinator.start_response(Session._create(socket), state, "in_unstarted", source())
    operation = next(iter(state.responses.values()))
    coordinator.barge_in(state, operation.response_id, "")
    coordinator.response_timeout(state, None, ["in_unstarted"])
    await asyncio.wait_for(coordinator.terminate_state(state, OperationOutcome.END_CALL), 2)
    assert not source_started
    assert not socket.frames
    assert not state.responses
    assert not state.input_responses
    assert state.input_resolution_tail is not None and state.input_resolution_tail.done()


@pytest.mark.asyncio
async def test_cancelled_sources_retain_capacity_until_cleanup_finishes() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import MAX_ACTIVE_RESPONSES, OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    coordinator = ResponseCoordinator()
    session = Session._create(DeclineHostSocket())
    release_cleanup = asyncio.Event()
    cleanup_finished = []

    async def source(started, cleanup_entered):
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_entered.set()
            await release_cleanup.wait()
            cleanup_finished.append(True)

    try:
        for index in range(MAX_ACTIVE_RESPONSES):
            started = asyncio.Event()
            entered = asyncio.Event()
            item_id = f"in_capacity_{index}"
            assert coordinator.start_response(session, state, item_id, source(started, entered))
            await asyncio.wait_for(started.wait(), 2)
            coordinator.response_timeout(state, None, [item_id])
            await asyncio.wait_for(entered.wait(), 2)
        assert state.active_response_count == MAX_ACTIVE_RESPONSES
        assert not coordinator.start_response(session, state, "in_overflow", "overflow")
        release_cleanup.set()
        await asyncio.wait_for(
            asyncio.gather(
                *(operation.task for operation in tuple(state.responses.values())),
                return_exceptions=True,
            ),
            2,
        )
        await asyncio.sleep(0)
        assert len(cleanup_finished) == MAX_ACTIVE_RESPONSES
        assert not state.input_responses
        assert coordinator.start_response(session, state, "in_recovered", "recovered")
        await asyncio.gather(*(operation.task for operation in tuple(state.responses.values())))
    finally:
        release_cleanup.set()
        await asyncio.wait_for(coordinator.terminate_state(state, OperationOutcome.END_CALL), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_point",
    ["source", "source_close", "created_send", "self_cancel_send", "decline_send", "error_send"],
)
async def test_upstream_exception_content_is_not_logged(failure_point, caplog) -> None:
    import logging
    import time

    from response_coordinator import ResponseCoordinator
    from state import InputOrigin, OperationOutcome, SessionState

    marker = "SYNTHETIC_CUSTOMER_PROMPT_AND_CREDENTIAL_DO_NOT_LOG"
    caplog.set_level(logging.DEBUG, logger="voice_live_bridge")

    def fail():
        raise RuntimeError(marker) from ValueError("nested_" + marker)

    class FailingSession:
        async def send(self, event):
            failure_type = {
                "created_send": "response.created",
                "self_cancel_send": "response.cancel",
                "decline_send": "response.none",
                "error_send": "error",
            }.get(failure_point)
            if event.type == failure_type:
                fail()

    async def source():
        try:
            yield "first"
            if failure_point in {"source", "error_send"}:
                fail()
        finally:
            if failure_point == "source_close":
                fail()

    coordinator = ResponseCoordinator()
    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    session = FailingSession()
    try:
        if failure_point == "self_cancel_send":
            assert coordinator.start_self_cancel(
                session, state, "in_private", "text", time.monotonic()
            )
        elif failure_point == "decline_send":
            coordinator.schedule_none(
                session, state, "in_private", InputOrigin.USER, reason="no_reply_needed"
            )
        else:
            assert coordinator.start_response(
                session, state, "in_private", source(), time.monotonic()
            )
        operations = tuple(state.responses.values())
        await asyncio.wait_for(
            asyncio.gather(*(operation.task for operation in operations)), 2
        )
        records = [record for record in caplog.records if record.name == "voice_live_bridge"]
        assert records, "Failures must still produce a diagnostic."
        for record in records:
            assert marker not in record.getMessage()
            assert marker not in repr(record.args)
            assert record.exc_info is None
            assert not record.stack_info
        assert any("RuntimeError" in record.getMessage() for record in records)
        assert operations[0].outcome is OperationOutcome.ERROR
    finally:
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
