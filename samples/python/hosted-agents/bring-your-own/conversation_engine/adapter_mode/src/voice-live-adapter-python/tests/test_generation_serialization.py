# Copyright (c) Microsoft. All rights reserved.

"""The Bridge permits one wire generation, independently of slow task cleanup."""

import asyncio
import json

import pytest
from starlette.responses import StreamingResponse

from adapter.response_coordinator import ResponseCoordinator
from adapter.runtime import create_app
from adapter.state import OperationOutcome, SessionState
from echo_agent import handle_invocation


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


@pytest.mark.parametrize("stage", ["before_output", "after_output", "cleanup"])
async def test_producer_cancellation_fails_before_the_next_generation(stage):
    coordinator, state, session = setup()
    closed, error_started, release_error = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_send = session.send

    async def send(event):
        if event.type == "error":
            error_started.set()
            await release_error.wait()
        await original_send(event)

    session.send = send

    async def cancelled_child():
        child = asyncio.create_task(asyncio.sleep(60))
        child.cancel("private upstream cancellation details")
        await child

    async def first():
        try:
            if stage != "before_output":
                yield "first"
            if stage != "cleanup":
                await cancelled_child()
        finally:
            try:
                if stage == "cleanup":
                    await cancelled_child()
            finally:
                closed.set()

    assert coordinator.start_response(session, state, "in_first", first(), response_id="r_first")
    first_op = state.responses["r_first"]
    assert coordinator.start_response(
        session, state, "in_second", one_chunk(), response_id="r_second"
    )
    second_op = state.responses["r_second"]
    try:
        await asyncio.wait_for(error_started.wait(), 2)
        assert closed.is_set()
        assert first_op.outcome is OperationOutcome.ERROR
        assert not first_op.cancellation_requested
        assert first_op.generation_owned
        assert not second_op.task.done()
        assert [
            event.response_id for event in session.sent if event.type == "response.created"
        ] == ["r_first"]
    finally:
        release_error.set()
        await join(first_op)
        await join(second_op)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)

    assert not session.violations
    assert [
        (event.type, event.response_id)
        for event in session.sent
        if event.type in {"response.created", "error", "response.done"}
    ] == [
        ("response.created", "r_first"),
        ("error", "r_first"),
        ("response.created", "r_second"),
        ("response.done", "r_second"),
    ]
    error = next(event for event in session.sent if event.type == "error")
    assert error.code == "generation_failed"
    assert error.message == "The response could not be generated."
    assert first_op.outcome is OperationOutcome.ERROR
    assert not state.responses and not state.input_responses
    assert not state.generation_gate.locked()


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


@pytest.mark.parametrize("behavior", ["cleanup_error", "continue", "return"])
@pytest.mark.parametrize("control", ["barge_in", "response_cancelled", "timeout", "session_end"])
async def test_winning_cancellation_suppresses_every_late_frame(behavior, control):
    coordinator, state, session = setup()
    started, interrupted, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    closed = asyncio.Event()

    async def first():
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        except asyncio.CancelledError:
            interrupted.set()
            await release.wait()
            if behavior == "cleanup_error":
                raise RuntimeError("synthetic cleanup failure") from None
            if behavior == "continue":
                yield "STALE"
            return
        finally:
            closed.set()

    assert coordinator.start_response(session, state, "in_first", first(), response_id="r_first")
    first_op = state.responses["r_first"]
    await asyncio.wait_for(started.wait(), 2)
    cut = len(session.sent)
    session.open_response = None  # The Bridge has already committed the winning terminal.
    termination = None
    if control == "session_end":
        termination = asyncio.create_task(
            coordinator.terminate_state(state, OperationOutcome.END_CALL)
        )
    elif control == "timeout":
        coordinator.response_timeout(state, "r_first", None)
    elif control == "barge_in":
        coordinator.barge_in(state, "r_first", "first")
    else:
        coordinator.response_cancelled(state, "r_first", "first")
    try:
        await asyncio.wait_for(interrupted.wait(), 2)
        if termination is None:
            assert coordinator.start_response(
                session, state, "in_second", one_chunk(), response_id="r_second"
            )
            await join(state.responses["r_second"])
        release.set()
        await join(first_op)
        assert closed.is_set()
        assert not [
            event for event in session.sent[cut:]
            if getattr(event, "response_id", None) == "r_first"
        ]
        assert not session.violations
    finally:
        release.set()
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
        if termination is not None:
            await asyncio.wait_for(termination, 2)


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


@pytest.mark.parametrize("data_only", [False, True])
async def test_real_sdk_dispatcher_never_opens_two_generations_for_queued_inputs(data_only):
    async def handler(request, _context, _signal):
        for word in request["input"].split():
            yield {"type": "response.output_text.delta", "delta": word + " "}

    app = create_app(handle_invocation, configure_observability=None)
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


async def test_real_sdk_adapter_reports_producer_cancellation_and_recovers():
    closed = asyncio.Event()

    async def handler(request):
        text = (await request.json())["input"]

        async def chunks():
            try:
                yield "data: " + json.dumps({"type": "token", "content": text}) + "\n\n"
                if text == "first":
                    child = asyncio.create_task(asyncio.sleep(60))
                    child.cancel("private upstream cancellation details")
                    await child
                yield "data: " + json.dumps({"type": "done", "full_text": text}) + "\n\n"
            finally:
                if text == "first":
                    closed.set()

        return StreamingResponse(chunks(), media_type="text/event-stream")

    app = create_app(handler, configure_observability=None)
    runtime, socket = app.state.voice_runtime, HostSocket()
    socket.enqueue(
        "session.start", protocol_version="1.0", reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30_000},
    )
    for text in ("first", "second"):
        socket.enqueue(
            "user.message", item_id=f"in_{text}", content=[{"type": "input_text", "text": text}]
        )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        async with asyncio.timeout(2):
            while not any(frame["type"] == "response.done" for frame in socket.frames):
                socket.changed.clear()
                await socket.changed.wait()
        assert [frame["type"] for frame in socket.frames] == [
            "session.ready", "response.created", "response.output_text.delta", "error",
            "response.created", "response.output_text.delta", "response.output_text.done",
            "response.done",
        ]
        first_id, second_id = socket.frames[1]["response_id"], socket.frames[4]["response_id"]
        assert first_id != second_id
        assert socket.frames[3]["response_id"] == first_id
        assert socket.frames[3]["message"] == "The response could not be generated."
        assert socket.frames[-1]["response_id"] == second_id
        assert closed.is_set()
    finally:
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.parametrize("behavior", ["cleanup_error", "continue", "return"])
@pytest.mark.parametrize("control", ["user.barge_in", "response.cancelled", "response.timeout"])
async def test_real_sdk_adapter_suppresses_cancelled_handler_frames(behavior, control):
    started, interrupted, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def handler(request):
        text = (await request.json())["input"]

        async def chunks():
            try:
                yield "data: " + json.dumps({"type": "token", "content": text}) + "\n\n"
                if text == "first":
                    started.set()
                    await asyncio.Future()
            except asyncio.CancelledError:
                interrupted.set()
                await release.wait()
                if behavior == "cleanup_error":
                    raise RuntimeError("synthetic cleanup failure") from None
                if behavior == "continue":
                    yield 'data: {"type":"token","content":"STALE"}\n\n'
                    text_after_cancel = text + "STALE"
                else:
                    text_after_cancel = text
                yield "data: " + json.dumps({
                    "type": "done", "full_text": text_after_cancel
                }) + "\n\n"
                return
            yield "data: " + json.dumps({"type": "done", "full_text": text}) + "\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    app = create_app(handler, configure_observability=None)
    runtime, socket = app.state.voice_runtime, HostSocket()
    socket.enqueue(
        "session.start", protocol_version="1.0", reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30_000},
    )
    socket.enqueue("user.message", item_id="in_first",
                   content=[{"type": "input_text", "text": "first"}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(started.wait(), 2)
        from azure.ai.agentserver.invocations.voice import Session

        first = next(iter(runtime._store.active(Session._current(socket)).responses.values()))
        cut = len(socket.frames)
        fields = {"stage": "idle"} if control == "response.timeout" else {"heard_text": "first"}
        socket.enqueue(control, response_id=first.response_id, **fields)
        await asyncio.wait_for(interrupted.wait(), 2)
        socket.enqueue("user.message", item_id="in_second",
                       content=[{"type": "input_text", "text": "second"}])
        async with asyncio.timeout(2):
            while not any(frame["type"] == "response.done" for frame in socket.frames):
                socket.changed.clear()
                await socket.changed.wait()
        release.set()
        await join(first)
        assert not [frame for frame in socket.frames[cut:]
                    if frame.get("response_id") == first.response_id]
        assert not any(frame["type"] == "error" for frame in socket.frames)
    finally:
        release.set()
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()
