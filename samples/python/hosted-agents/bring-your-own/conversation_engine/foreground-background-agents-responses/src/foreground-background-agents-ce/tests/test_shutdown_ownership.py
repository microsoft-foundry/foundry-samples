# Copyright (c) Microsoft. All rights reserved.

"""Real SDK callbacks must not own the lifetime of asynchronous finalization."""

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect
from test_producer_ownership import Producer
from test_voice_runtime import (
    DeclineHostSocket as HostSocket,
)
from test_voice_runtime import (
    _enqueue_decline_start as enqueue_start,
)

from voice_runtime import create_app


def make_app():
    async def unused_handler(*_args):
        yield {"type": "response.output_text.delta", "delta": "unused"}

    return create_app(handler=unused_handler, configure_observability=None)


async def wait_frame(socket, kind):
    async with asyncio.timeout(2):
        while not any(frame["type"] == kind for frame in socket.frames):
            socket.changed.clear()
            await socket.changed.wait()


@pytest.mark.parametrize("mode", ["session_end", "disconnect", "close", "close_many", "no_input"])
async def test_cancelled_join_keeps_finalization_owned_until_later_close(mode, monkeypatch):
    app = make_app()
    runtime = app.state.voice_runtime
    release = asyncio.Event()
    source_created, termination_started = asyncio.Event(), asyncio.Event()
    sources, operations, sockets, connections = [], [], [], []
    marked_states = []
    original_mark = runtime._coordinator._mark_terminating

    def mark(state, outcome):
        tasks = original_mark(state, outcome)
        marked_states.append(state)
        if len(marked_states) == len(sockets):
            termination_started.set()
        return tasks

    monkeypatch.setattr(runtime._coordinator, "_mark_terminating", mark)

    async def owned_input(session, event):
        source = Producer(gate=release)
        sources.append(source)
        state = runtime._store.active(session)
        assert runtime._coordinator.start_response(session, state, event.item_id, source)
        operations.append(next(iter(state.responses.values())))
        source_created.set()

    app._voice_callbacks["user.message"] = owned_input
    joining = None
    try:
        for index in range(2 if mode == "close_many" else 1):
            socket = HostSocket()
            sockets.append(socket)
            enqueue_start(socket)
            connections.append(asyncio.create_task(app._handle_voice_connection(socket)))
            await wait_frame(socket, "session.ready")
            source_created.clear()
            socket.enqueue("user.message", item_id=f"in_owned_{index}",
                           content=[{"type": "input_text", "text": "test"}])
            await asyncio.wait_for(source_created.wait(), 2)
        for source in sources:
            await asyncio.wait_for(source.close_started.wait(), 2)

        if mode == "session_end":
            sockets[0].enqueue("session.end", reason="test_complete")
            joining = connections[0]
        elif mode == "disconnect":
            sockets[0].incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})
            with pytest.raises(WebSocketDisconnect):
                await asyncio.wait_for(connections[0], 2)
            joining = asyncio.create_task(runtime.close())
        elif mode == "no_input":
            sockets[0].enqueue("user.no_input", item_id="in_silence", count=3)
            await wait_frame(sockets[0], "end_call")
            assert not sources[0].closed
            joining = asyncio.create_task(runtime.close())
        else:
            joining = asyncio.create_task(runtime.close())

        await asyncio.wait_for(termination_started.wait(), 2)
        joining.cancel()
        with pytest.raises(asyncio.CancelledError):
            await joining

        # Repeated cancellation of joins must not cancel the retained cleanup owner.
        for _ in range(2):
            joining = asyncio.create_task(runtime.close())
            for _ in range(4):
                await asyncio.sleep(0)
            assert not joining.done(), "close returned while producer finalization was pending"
            assert runtime._coordinator._detached_tasks
            assert not any(source.closed for source in sources)
            assert all(operation.task.cancelling() == 1 for operation in operations)
            joining.cancel()
            with pytest.raises(asyncio.CancelledError):
                await joining

        joining = asyncio.create_task(runtime.close())
        release.set()
        await asyncio.wait_for(joining, 2)
        assert all(source.closed and source.close_calls == 1 for source in sources)
        assert not runtime._coordinator._detached_tasks
        assert not runtime._store._states
        assert not any(frame["type"] == "response.done"
                       for socket in sockets for frame in socket.frames)
    finally:
        release.set()
        await asyncio.gather(*(operation.output_cleanup for operation in operations
                               if operation.output_cleanup is not None), return_exceptions=True)
        for socket, connection in zip(sockets, connections, strict=True):
            if not connection.done():
                socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(asyncio.gather(*connections, return_exceptions=True), 2)
        if joining is not None:
            await asyncio.gather(joining, return_exceptions=True)
        await runtime.close()
