# Copyright (c) Microsoft. All rights reserved.

"""The Bridge permits one wire generation, independently of slow task cleanup."""

import asyncio
import json

import pytest

from response_coordinator import ResponseCoordinator
from state import OperationOutcome, SessionState
from voice_runtime import create_app


class WireSession:
    def __init__(self):
        self.open_response = None
        self.sent = []
        self.violations = []
        self.cancel_requested = asyncio.Event()

    async def send(self, event):
        if event.type == "response.created":
            if self.open_response is not None:
                self.violations.append("response_created_while_open")
            self.open_response = event.response_id
        elif event.type in {"response.done", "error"}:
            if event.response_id != self.open_response:
                self.violations.append("unbound_terminal")
            self.open_response = None
        elif event.type.startswith("response.output_") and event.response_id != self.open_response:
            self.violations.append("unbound_output")
        self.sent.append(event)
        if event.type == "response.cancel":
            self.cancel_requested.set()


def setup():
    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    return ResponseCoordinator(), state, WireSession()


async def one_chunk():
    yield "second"


async def join(operation):
    await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), 2)
    await asyncio.sleep(0)


@pytest.mark.parametrize("already_open", [False, True])
async def test_reply_waits_for_previous_generation_done(already_open):
    coordinator, state, session = setup()
    started, release = asyncio.Event(), asyncio.Event()

    async def first():
        yield "first"
        started.set()
        await release.wait()

    if already_open:
        session.open_response = "r_first"  # A proactive response has already been accepted.
    assert coordinator.start_response(
        session,
        state,
        None if already_open else "in_first",
        first(),
        response_id="r_first",
        response_started=already_open,
    )
    first_op = state.responses["r_first"]
    await asyncio.wait_for(started.wait(), 2)
    assert coordinator.start_response(
        session, state, "in_second", one_chunk(), response_id="r_second"
    )
    second_op = state.responses["r_second"]
    try:
        await asyncio.sleep(0)
        assert [
            event.response_id for event in session.sent if event.type == "response.created"
        ] == ([] if already_open else ["r_first"])
        assert state.active_response_count == 2  # Queued work still consumes bounded capacity.
    finally:
        release.set()
        await join(first_op)
        await join(second_op)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    assert not session.violations
    decisions = [
        (event.type, event.response_id)
        for event in session.sent
        if event.type in {"response.created", "response.done"}
    ]
    expected = [] if already_open else [("response.created", "r_first")]
    assert decisions == [
        *expected,
        ("response.done", "r_first"),
        ("response.created", "r_second"),
        ("response.done", "r_second"),
    ]


@pytest.mark.parametrize("control", ["barge_in", "response_cancelled", "timeout"])
async def test_winning_terminal_releases_generation_before_slow_cleanup(control):
    coordinator, state, session = setup()
    started, cleanup_started, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def first():
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    assert coordinator.start_response(session, state, "in_first", first(), response_id="r_first")
    first_op = state.responses["r_first"]
    await asyncio.wait_for(started.wait(), 2)
    assert coordinator.start_response(
        session, state, "in_second", one_chunk(), response_id="r_second"
    )
    second_op = state.responses["r_second"]
    try:
        await asyncio.sleep(0)
        session.open_response = None  # The inbound terminal has already won at the Bridge.
        if control == "timeout":
            coordinator.response_timeout(state, "r_first", None)
        elif control == "barge_in":
            coordinator.barge_in(state, "r_first", "heard")
        else:
            coordinator.response_cancelled(state, "r_first", "heard")
        await asyncio.wait_for(cleanup_started.wait(), 2)
        await join(second_op)
        assert not first_op.task.done()
        assert state.responses["r_first"] is first_op
        assert session.sent[-1].type == "response.done"
        assert session.sent[-1].response_id == "r_second"
        assert not session.violations
    finally:
        release_cleanup.set()
        await join(first_op)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)


async def test_self_cancel_holds_generation_until_winning_terminal_acknowledgment():
    coordinator, state, session = setup()
    assert coordinator.start_self_cancel(session, state, "in_self", "first", 0.0)
    first_op = next(iter(state.responses.values()))
    await asyncio.wait_for(session.cancel_requested.wait(), 2)
    assert coordinator.start_response(
        session, state, "in_second", one_chunk(), response_id="r_second"
    )
    second_op = state.responses["r_second"]
    try:
        await asyncio.sleep(0)
        assert sum(event.type == "response.created" for event in session.sent) == 1
        session.open_response = None
        coordinator.response_cancelled(state, first_op.response_id, "heard")
        await join(first_op)
        await join(second_op)
        assert not session.violations
        assert session.sent[-1].response_id == "r_second"
    finally:
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)


class HostSocket:
    def __init__(self):
        self.scope = {}
        self.frames = []
        self.incoming = asyncio.Queue()
        self.changed = asyncio.Event()
        self.sequence = 0

    def enqueue(self, kind, **fields):
        self.sequence += 1
        frame = {
            "type": kind,
            "id": f"m_serial_{self.sequence}",
            "ts": "2026-11-04T00:00:00Z",
            **fields,
        }
        self.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps(frame)})

    async def receive(self):
        return await self.incoming.get()

    async def send_text(self, text):
        self.frames.append(json.loads(text))
        self.changed.set()


@pytest.mark.parametrize("data_only", [False])
async def test_real_sdk_dispatcher_never_opens_two_generations_for_queued_inputs(data_only):
    async def handler(request, _context, _signal):
        for word in request["input"].split():
            yield {"type": "response.output_text.delta", "delta": word + " "}

    app = create_app(handler=handler, configure_observability=None)
    runtime, socket = app.state.voice_runtime, HostSocket()
    socket.enqueue(
        "session.start",
        protocol_version="1.0",
        reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30_000},
    )
    for index in range(2):
        content = (
            {"type": "input_data", "data": {"index": index}}
            if data_only
            else {"type": "input_text", "text": "word " * 100}
        )
        socket.enqueue("user.message", item_id=f"in_{index}", content=[content])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        async with asyncio.timeout(2):
            while sum(frame["type"] == "response.done" for frame in socket.frames) != 2:
                socket.changed.clear()
                await socket.changed.wait()
        open_response = None
        for frame in socket.frames:
            if frame["type"] == "response.created":
                assert open_response is None, socket.frames
                open_response = frame["response_id"]
            elif frame["type"] == "response.done":
                assert open_response == frame["response_id"]
                open_response = None
            else:
                assert frame["type"] != "error", frame
        assert open_response is None
    finally:
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()
