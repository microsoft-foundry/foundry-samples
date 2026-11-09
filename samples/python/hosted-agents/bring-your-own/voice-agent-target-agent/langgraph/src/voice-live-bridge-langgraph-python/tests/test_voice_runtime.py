# Copyright (c) Microsoft. All rights reserved.

"""Wire-level tests for the LangGraph Python Voice Live Bridge sample."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from response_coordinator import ResponseCoordinator
from scripts.smoke_test import ResponseValidator
from state import (
    MAX_ACTIVE_RESPONSES,
    MAX_PENDING_PROACTIVE,
    MAX_SEEN_INPUTS,
    MAX_TERMINAL_SENDS,
    InputClaim,
    InputOrigin,
    ModelMessage,
    SessionState,
)
from voice_runtime import IDLE_REMINDER_TEXT, VoiceRuntime, create_app


@dataclass(slots=True)
class BlockingScript:
    first_chunk: str
    started: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)


class FakeModel:
    model_name = "fake-model"
    server_address = "fake.example"

    def __init__(self, scripts: Sequence[list[str] | BaseException | BlockingScript]) -> None:
        self._scripts = list(scripts)
        self.requests: list[tuple[ModelMessage, ...]] = []
        self.closed = False
        self.close_count = 0

    async def complete(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        self.requests.append(tuple(messages))
        script = self._scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        if isinstance(script, BlockingScript):
            script.started.set()
            try:
                yield script.first_chunk
                await asyncio.Future()
            except asyncio.CancelledError:
                script.cancelled.set()
                raise
        else:
            for chunk in script:
                await asyncio.sleep(0)
                yield chunk

    async def close(self) -> None:
        self.close_count += 1
        self.closed = True


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


def pairs(messages: Sequence[ModelMessage]) -> list[tuple[str, str]]:
    return [(message.role, message.content) for message in messages]


def test_streams_model_output_and_commits_history() -> None:
    model = FakeModel([["Hello", " there"], ["Second"]])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_1", "First question")
        first = receive_until(ws, "response.done")
        assert [item["type"] for item in first] == [
            "response.created",
            "response.output_text.delta",
            "response.output_text.delta",
            "response.output_text.done",
            "response.done",
        ]
        assert first[-2]["text"] == "Hello there"

        send_user(ws, "in_2", "Second question")
        receive_until(ws, "response.done")

    assert pairs(model.requests[1]) == [
        ("user", "First question"),
        ("assistant", "Hello there"),
        ("user", "Second question"),
    ]
    assert model.closed


def test_protocol_mismatch_is_rejected() -> None:
    model = FakeModel([])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        rejected = start(ws, protocol="2.0")
        assert rejected["type"] == "session.rejected"
        assert rejected["code"] == "protocol_mismatch"
        send_user(ws, "in_after_rejection", "must not run")

    assert model.requests == []


def test_input_before_session_start_is_ignored() -> None:
    model = FakeModel([])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        send_user(ws, "in_before_start", "must not run")

    assert model.requests == []


def test_proactive_waits_for_acceptance() -> None:
    model = FakeModel([["Proactive answer"]])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_proactive", "/proactive Check in")
        assert ws.receive_json()["type"] == "response.none"
        admission = ws.receive_json()
        assert admission["type"] == "response.created"
        assert "in_reply_to" not in admission
        assert model.requests == []

        ws.send_json(frame("response.accepted", response_id=admission["response_id"]))
        receive_until(ws, "response.done")

    assert pairs(model.requests[0]) == [("user", "Check in")]


def test_barge_in_cancels_and_reconciles_heard_text() -> None:
    blocked = BlockingScript("unplayed")
    model = FakeModel([blocked, ["next"]])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
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
        receive_until(ws, "response.done")

    assert pairs(model.requests[1]) == [
        ("user", "Tell me a story"),
        ("assistant", "The part heard."),
        ("user", "Continue"),
    ]


def test_no_input_reminder_and_end_call() -> None:
    app = create_app(FakeModel([]), configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        ws.send_json(frame("user.no_input", item_id="in_idle_1", count=1))
        reminder = receive_until(ws, "response.done")
        assert reminder[-2]["text"] == IDLE_REMINDER_TEXT

        ws.send_json(frame("user.no_input", item_id="in_idle_3", count=3))
        end = receive_type(ws, "end_call")
        assert end["mode"] == "drain"


@pytest.mark.asyncio
async def test_runtime_closes_owned_model_once() -> None:
    model = FakeModel([])
    runtime = VoiceRuntime(model)

    await runtime.close()
    await runtime.close()

    assert model.close_count == 1


def test_input_after_session_end_is_ignored() -> None:
    model = FakeModel([])
    app = create_app(model, configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        ws.send_json(frame("session.end", reason="caller_hangup"))
        send_user(ws, "in_after_end", "must not run")

    assert model.requests == []


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
    coordinator = ResponseCoordinator(FakeModel([]))
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
    coordinator = ResponseCoordinator(FakeModel([]))
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
    coordinator = ResponseCoordinator(FakeModel([]))

    assert coordinator.start_response(
        session,  # type: ignore[arg-type]
        state,
        "in_1",
        text="complete",
        use_model=False,
        streaming=False,
        voice=None,
        origin=InputOrigin.USER,
    )
    operation = next(iter(state.responses.values()))
    assert operation.task is not None
    await operation.task

    assert session.capacity_at_done == 0


@pytest.mark.parametrize(("command", "mode"), [("/end", "drain"), ("/end-now", "immediate")])
def test_end_commands_cancel_active_work_before_end_call(command: str, mode: str) -> None:
    blocked = BlockingScript("partial")
    app = create_app(FakeModel([blocked]), configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_blocked", "Start work")
        receive_type(ws, "response.output_text.delta")
        send_user(ws, "in_end", command)
        end = receive_type(ws, "end_call")
        assert blocked.cancelled.is_set()
        assert end["mode"] == mode


def test_third_no_input_cancels_active_work_before_end_call() -> None:
    blocked = BlockingScript("partial")
    app = create_app(FakeModel([blocked]), configure_observability=None)

    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_blocked", "Start work")
        receive_type(ws, "response.output_text.delta")
        ws.send_json(frame("user.no_input", item_id="in_idle_3", count=3))
        assert receive_type(ws, "end_call")["mode"] == "drain"
        assert blocked.cancelled.is_set()


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