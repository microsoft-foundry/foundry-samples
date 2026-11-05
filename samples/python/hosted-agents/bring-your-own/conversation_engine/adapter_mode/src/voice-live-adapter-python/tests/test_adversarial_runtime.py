# Copyright (c) Microsoft. All rights reserved.

"""Adversarial lifecycle tests using the real SDK host and local transport gates."""

import asyncio
import json
import logging
import random
from types import SimpleNamespace

import pytest
from azure.ai.agentserver.invocations.voice import InputTextPart, Session
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from adapter import invocation
from adapter.response_coordinator import ResponseCoordinator
from adapter.runtime import VoiceRuntime, create_app
from adapter.state import (
    MAX_ACTIVE_RESPONSES,
    MAX_PENDING_DECLINES,
    InputOrigin,
    OperationOutcome,
    SessionState,
)
from echo_agent import handle_invocation


class Socket:
    def __init__(self):
        self.scope = {}
        self.frames = []
        self.changed = asyncio.Event()

    async def send_text(self, text):
        self.frames.append(json.loads(text))
        self.changed.set()


class HostSocket(Socket):
    def __init__(self):
        super().__init__()
        self.incoming = asyncio.Queue()
        self.none_started = asyncio.Event()
        self.release_none = asyncio.Event()
        self.release_none.set()
        self.sequence = 0

    async def receive(self):
        return await self.incoming.get()

    def enqueue(self, kind, **fields):
        self.sequence += 1
        frame = {
            "type": kind,
            "id": f"m_probe_{self.sequence}",
            "ts": "2026-11-02T00:00:00Z",
            **fields,
        }
        self.incoming.put_nowait({"type": "websocket.receive", "text": json.dumps(frame)})

    async def send_text(self, text):
        frame = json.loads(text)
        if frame["type"] == "response.none":
            self.none_started.set()
            await self.release_none.wait()
        self.frames.append(frame)
        self.changed.set()


async def wait_until(socket, predicate):
    async with asyncio.timeout(1):
        while not predicate():
            socket.changed.clear()
            await socket.changed.wait()


def enqueue_start(socket):
    socket.enqueue(
        "session.start",
        protocol_version="1.0",
        reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30000},
    )


@pytest.fixture(autouse=True)
def context(monkeypatch):
    monkeypatch.setattr(
        invocation,
        "get_request_context",
        lambda: SimpleNamespace(
            session_id="local-session", user_id="local-user", call_id="local-call"
        ),
    )


async def test_back_to_back_inputs_preserve_wire_resolution_order_through_real_host():
    socket = HostSocket()
    app = create_app(handle_invocation, configure_observability=None)
    runtime = app.state.voice_runtime
    enqueue_start(socket)
    socket.enqueue(
        "user.message", item_id="in_first", content=[{"type": "input_text", "text": "first"}]
    )
    socket.enqueue(
        "user.message", item_id="in_second", content=[{"type": "input_text", "text": ""}]
    )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await wait_until(
            socket, lambda: sum("in_reply_to" in frame for frame in socket.frames) == 2
        )
        resolved = [item for frame in socket.frames for item in frame.get("in_reply_to", [])]
        assert resolved == ["in_first", "in_second"], socket.frames
    finally:
        socket.enqueue("session.end", reason="probe_complete")
        await asyncio.wait_for(connection, 1)
        await runtime.close()


async def test_blocked_decline_does_not_block_response_timeout_callback():
    socket = HostSocket()
    socket.release_none.clear()
    app = create_app(handle_invocation, configure_observability=None)
    runtime = app.state.voice_runtime
    timeout_handled = asyncio.Event()
    callback = app._voice_callbacks["response.timeout"]

    async def observe_timeout(session, event):
        timeout_handled.set()
        await callback(session, event)

    app._voice_callbacks["response.timeout"] = observe_timeout
    enqueue_start(socket)
    socket.enqueue("user.message", item_id="in_empty", content=[{"type": "input_text", "text": ""}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(socket.none_started.wait(), 1)
        socket.enqueue("response.timeout", stage="first_output", item_ids=["in_empty"])
        await asyncio.sleep(0.05)
        assert timeout_handled.is_set(), "the receive loop is blocked in response.none send"
    finally:
        socket.release_none.set()
        socket.enqueue("session.end", reason="probe_complete")
        await asyncio.wait_for(connection, 1)
        await runtime.close()


async def test_barge_in_then_cancelled_event_does_not_abort_async_cleanup():
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleaned = False

    async def background():
        nonlocal cleaned
        cleanup_started.set()
        await release_cleanup.wait()
        cleaned = True

    async def handler(_request):
        async def chunks():
            yield 'data: {"type":"token","content":"first"}\n\n'
            await asyncio.Future()

        return StreamingResponse(
            chunks(), media_type="text/event-stream", background=BackgroundTask(background)
        )

    socket = HostSocket()
    app = create_app(handler, configure_observability=None)
    runtime = app.state.voice_runtime
    cancelled_handled = asyncio.Event()
    callback = app._voice_callbacks["response.cancelled"]

    async def observe_cancelled(session, event):
        await callback(session, event)
        cancelled_handled.set()

    app._voice_callbacks["response.cancelled"] = observe_cancelled
    enqueue_start(socket)
    socket.enqueue(
        "user.message", item_id="in_cancel", content=[{"type": "input_text", "text": "test"}]
    )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await wait_until(
            socket,
            lambda: any(frame["type"] == "response.output_text.delta" for frame in socket.frames),
        )
        session = Session._current(socket)
        state = runtime._store.active(session)
        operation = next(iter(state.responses.values()))
        socket.enqueue("user.barge_in", response_id=operation.response_id, heard_text="first")
        await asyncio.wait_for(cleanup_started.wait(), 1)
        socket.enqueue("response.cancelled", response_id=operation.response_id, heard_text="first")
        await asyncio.wait_for(cancelled_handled.wait(), 1)
        release_cleanup.set()
        await asyncio.gather(operation.task, return_exceptions=True)
        assert cleaned, "a repeated cancellation interrupted background cleanup"
    finally:
        release_cleanup.set()
        socket.enqueue("session.end", reason="probe_complete")
        await asyncio.wait_for(connection, 1)
        await runtime.close()


async def test_customer_exception_content_is_not_logged(caplog):
    marker = "SYNTHETIC_PRIVATE_INPUT_DO_NOT_LOG"

    async def handler(_request):
        raise ValueError(marker)

    socket = Socket()
    session = Session._create(socket)
    runtime = VoiceRuntime(handler)
    try:
        with caplog.at_level(logging.ERROR, logger="voice_live_bridge"):
            await runtime.on_session_start(session, SimpleNamespace(protocol_version="1.0"))
            await runtime.on_user_message(
                session, SimpleNamespace(item_id="in_error", content=[InputTextPart(text="test")])
            )
            state = runtime._store.active(session)
            await asyncio.gather(*(op.task for op in list(state.responses.values())))
        assert marker not in caplog.text
        assert any(frame.get("type") == "error" for frame in socket.frames)
    finally:
        await runtime.close()


@pytest.mark.parametrize("control", ["user.barge_in", "response.cancelled", "response.timeout"])
@pytest.mark.parametrize("kind", ["token", "data"])
async def test_blocked_output_keeps_backend_cleanup_in_tracked_response(control, kind):
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    body_closed = asyncio.Event()
    cleanups = 0

    async def background():
        nonlocal cleanups
        cleanups += 1
        cleanup_started.set()
        await release_cleanup.wait()

    async def handler(_request):
        async def chunks():
            try:
                fields = {"content": "first"} if kind == "token" else {"data": {"value": 1}}
                yield "data: " + json.dumps({"type": kind, **fields}) + "\n\n"
                await asyncio.Future()
            finally:
                body_closed.set()

        return StreamingResponse(
            chunks(), media_type="text/event-stream", background=BackgroundTask(background)
        )

    class BlockedOutputSocket(HostSocket):
        def __init__(self):
            super().__init__()
            self.output_started = asyncio.Event()

        async def send_text(self, text):
            if json.loads(text)["type"] in {
                "response.output_text.delta", "response.output_data.done"
            }:
                self.output_started.set()
                await asyncio.Future()
            await super().send_text(text)

    socket = BlockedOutputSocket()
    app = create_app(handler, configure_observability=None)
    runtime = app.state.voice_runtime
    enqueue_start(socket)
    socket.enqueue(
        "user.message", item_id="in_cleanup", content=[{"type": "input_text", "text": "test"}]
    )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    closing = None
    try:
        await asyncio.wait_for(socket.output_started.wait(), 1)
        state = runtime._store.active(Session._current(socket))
        operation = next(iter(state.responses.values()))
        fields = {"response_id": operation.response_id}
        fields.update(
            {"stage": "max_duration"} if control == "response.timeout" else {"heard_text": ""}
        )
        socket.enqueue(control, **fields)
        await asyncio.wait_for(cleanup_started.wait(), 1)
        assert body_closed.is_set()
        assert not operation.task.done(), "backend cleanup escaped the tracked response task"
        assert state.active_response_count == 1
        assert state.input_responses["in_cleanup"] == operation.response_id

        socket.enqueue("session.end", reason="test_complete")
        # Shutdown must also wait for already-cancelled work, without cancelling cleanup again.
        closing = asyncio.create_task(runtime.close())
        await asyncio.sleep(0)
        assert not closing.done()
        assert not connection.done()
        assert not operation.task.done()
        release_cleanup.set()
        await asyncio.wait_for(asyncio.gather(connection, closing), 1)
        assert operation.task.done()
        assert cleanups == 1
        assert not state.responses
        assert not state.input_responses
        assert state.active_response_count == 0
        assert not any(frame["type"] == "response.done" for frame in socket.frames)
    finally:
        release_cleanup.set()
        if not connection.done():
            socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 1)
        if closing is not None:
            await asyncio.wait_for(closing, 1)
        await runtime.close()


async def test_sse_profile_handles_all_split_positions_and_random_partitions():
    text = " 你好 👋\tZ\n"
    token = json.dumps({"type": "token", "content": text}, ensure_ascii=False)
    done = json.dumps({"type": "done", "full_text": text}, ensure_ascii=False)
    raw = (": heartbeat\r\n\r\ndata: " + token + "\r\n\r\ndata: " + done + "\r\n\r\n").encode()
    partitions = [[raw[:split], raw[split:]] for split in range(len(raw) + 1)]
    rng = random.Random(1124)
    for _ in range(100):
        cuts = sorted({0, len(raw), *(rng.randrange(len(raw) + 1) for _ in range(15))})
        partitions.append([raw[left:right] for left, right in zip(cuts, cuts[1:], strict=False)])
    for partition in partitions:

        async def handler(_request, chunks_for_response=partition):
            async def chunks():
                for chunk in chunks_for_response:
                    yield chunk

            return StreamingResponse(chunks(), media_type="text/event-stream")

        result = "".join(
            [part async for part in invocation.InvocationAdapter(handler).stream("test", "in_sse")]
        )
        assert result == text


async def test_declines_are_bounded_and_cancelled_before_the_worker_starts():
    socket = Socket()
    session = Session._create(socket)
    state = SessionState()
    state.try_begin_start()
    state.activate()
    coordinator = ResponseCoordinator()
    for index in range(MAX_PENDING_DECLINES):
        coordinator.schedule_none(
            session, state, f"in_{index}", InputOrigin.USER, reason="empty_input"
        )
    assert state.pending_decline_count == MAX_PENDING_DECLINES
    assert state.active_response_count == 0
    with pytest.raises(RuntimeError, match="capacity exceeded"):
        coordinator.schedule_none(
            session, state, "in_overflow", InputOrigin.USER, reason="empty_input"
        )
    await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    assert not socket.frames
    assert not state.responses
    assert not state.input_responses


async def test_timeout_of_queued_resolution_preserves_later_input_order():
    socket = HostSocket()
    socket.release_none.clear()
    session = Session._create(socket)
    runtime = VoiceRuntime(handle_invocation)
    await runtime.on_session_start(session, SimpleNamespace(protocol_version="1.0"))
    state = runtime._store.active(session)
    try:
        for item_id, text in [("in_first", ""), ("in_cancel", "unused"), ("in_last", "last")]:
            await runtime.on_user_message(
                session, SimpleNamespace(item_id=item_id, content=[InputTextPart(text=text)])
            )
        await asyncio.wait_for(socket.none_started.wait(), 1)
        runtime._coordinator.response_timeout(state, None, ["in_cancel"])
        socket.release_none.set()
        await asyncio.gather(
            *(op.task for op in list(state.responses.values())), return_exceptions=True
        )
        resolved = [item for frame in socket.frames for item in frame.get("in_reply_to", [])]
        assert resolved == ["in_first", "in_last"]
        assert not state.input_responses
    finally:
        socket.release_none.set()
        await runtime.close()


async def test_cancelled_sources_keep_capacity_and_are_drained_on_termination():
    coordinator = ResponseCoordinator()
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = Session._create(Socket())
    release_cleanup = asyncio.Event()
    closed = []

    async def source(index, started, cleanup_entered):
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_entered.set()
            await release_cleanup.wait()
            closed.append(index)

    termination = None
    try:
        for index in range(MAX_ACTIVE_RESPONSES):
            started = asyncio.Event()
            cleanup_entered = asyncio.Event()
            input_id = f"in_cleanup_{index}"
            assert coordinator.start_response(
                session, state, input_id, source(index, started, cleanup_entered)
            )
            await asyncio.wait_for(started.wait(), 1)
            coordinator.cancel_response(
                state, state.input_responses[input_id], OperationOutcome.CANCELLED
            )
            await asyncio.wait_for(cleanup_entered.wait(), 1)
        assert state.active_response_count == MAX_ACTIVE_RESPONSES
        assert not state.can_start_response()
        termination = asyncio.create_task(
            coordinator.terminate_state(state, OperationOutcome.END_CALL)
        )
        await asyncio.sleep(0)
        assert not termination.done()
        release_cleanup.set()
        await asyncio.wait_for(termination, 1)
        assert sorted(closed) == list(range(MAX_ACTIVE_RESPONSES))
        assert not state.responses
    finally:
        release_cleanup.set()
        if termination is not None:
            await termination
        else:
            await coordinator.terminate_state(state, OperationOutcome.CANCELLED)
