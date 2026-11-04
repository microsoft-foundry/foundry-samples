# Copyright (c) Microsoft. All rights reserved.

"""Exercise overlapping turns and input admission through the real CE dispatcher."""

import asyncio
from types import SimpleNamespace

import pytest
from azure.ai.agentserver.invocations.voice import InputTextPart, Session
from test_voice_runtime import DeclineHostSocket, _enqueue_decline_start, _wait_for_decline_event

from task_store import TaskStatus
from voice_runtime import Conversation, VoiceRuntime, create_app


async def test_pre_start_timeout_removes_signal_without_starting_handler():
    calls = []

    async def handler(*_args):
        calls.append(True)
        yield {"type": "response.output_text.delta", "delta": "unexpected"}

    class LocalSession:
        async def send(self, _event):
            pass

    runtime, session = VoiceRuntime(handler), LocalSession()
    state = runtime._store.get_or_create(session)
    assert state.try_begin_start()
    state.activate()
    conversation = Conversation()
    runtime._conversations[session] = conversation
    await runtime.on_user_message(session, SimpleNamespace(
        item_id="in_queued", content=[InputTextPart(text="hello")]
    ))
    operation = next(iter(state.responses.values()))
    await runtime.on_response_timeout(session, SimpleNamespace(
        response_id=operation.response_id, item_ids=()
    ))
    await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), 2)
    await asyncio.sleep(0)
    assert not calls
    assert not state.responses
    assert not conversation.signals
    await runtime.close()


def texts(history):
    return [part["text"] for item in history for part in item["content"]]


@pytest.mark.parametrize("control", ["user.barge_in", "response.cancelled", "response.timeout"])
@pytest.mark.parametrize("heard", ["old heard", ""])
async def test_next_turn_sees_committed_history_before_interrupted_cleanup_finishes(control, heard):
    cleanup_started, release_cleanup = asyncio.Event(), asyncio.Event()
    snapshots = []

    async def handler(request, context, _signal):
        if request["input"] == "old question":
            try:
                yield {"type": "response.output_text.delta", "delta": "old answer"}
                await asyncio.Future()
            finally:
                cleanup_started.set()
                await release_cleanup.wait()
        else:
            snapshots.append(context.history)
            yield {"type": "response.output_text.delta", "delta": "new answer"}

    app = create_app(handler=handler, configure_observability=None)
    runtime = app.state.voice_runtime
    socket = DeclineHostSocket()
    _enqueue_decline_start(socket)
    socket.enqueue("user.message", item_id="in_old",
                   content=[{"type": "input_text", "text": "old question"}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await _wait_for_decline_event(socket, lambda: any(
            frame["type"] == "response.output_text.delta" for frame in socket.frames
        ))
        session = Session._current(socket)
        conversation = runtime._conversations[session]
        operation = next(iter(runtime._store.active(session).responses.values()))
        fields = {"response_id": operation.response_id}
        fields.update({"stage": "max_duration"} if control == "response.timeout"
                      else {"heard_text": heard})
        socket.enqueue(control, **fields)
        await asyncio.wait_for(cleanup_started.wait(), 2)
        assert not operation.task.done()
        socket.enqueue("user.message", item_id="in_new",
                       content=[{"type": "input_text", "text": "new question"}])
        await _wait_for_decline_event(socket, lambda: any(
            frame["type"] == "response.done" for frame in socket.frames
        ))
        expected_old = "old answer" if control == "response.timeout" else heard
        previous = ["old question"] + ([expected_old] if expected_old else [])
        assert texts(snapshots[0]) == previous
        assert texts(conversation.history) == previous + ["new question", "new answer"]
        release_cleanup.set()
        await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), 2)
        assert texts(conversation.history) == previous + ["new question", "new answer"]
        assert texts(snapshots[0]) == previous  # Snapshots must not mutate retroactively.
    finally:
        release_cleanup.set()
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.parametrize(
    "terminal", ["complete", "user.barge_in", "response.cancelled", "response.timeout"]
)
async def test_queued_history_freezes_latest_prior_turns_without_future_inputs(terminal):
    finish_first, release_cleanup = asyncio.Event(), asyncio.Event()
    cleanup_started, queued = asyncio.Event(), asyncio.Event()
    snapshots = {}

    async def handler(request, context, _signal):
        if request["input"] == "old question":
            try:
                yield {"type": "response.output_text.delta", "delta": "first part"}
                await finish_first.wait()
                yield {"type": "response.output_text.delta", "delta": " rest"}
            finally:
                cleanup_started.set()
                await release_cleanup.wait()
        else:
            snapshots[request["input"]] = await context.get_history()
            answer = "second answer" if request["input"] == "second question" else "third answer"
            yield {"type": "response.output_text.delta", "delta": answer}

    app = create_app(handler=handler, configure_observability=None)
    runtime = app.state.voice_runtime
    original = app._voice_callbacks["user.message"]

    async def observe_queued(session, event):
        await original(session, event)
        if event.item_id == "in_third":
            queued.set()

    app._voice_callbacks["user.message"] = observe_queued
    socket = DeclineHostSocket()
    _enqueue_decline_start(socket)
    socket.enqueue("user.message", item_id="in_old",
                   content=[{"type": "input_text", "text": "old question"}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.output_text.delta" for event in socket.frames
        ))
        state = runtime._store.active(Session._current(socket))
        first = state.responses[state.input_responses["in_old"]]
        for item_id, text in [("in_second", "second question"), ("in_third", "future question")]:
            socket.enqueue("user.message", item_id=item_id,
                           content=[{"type": "input_text", "text": text}])
        await asyncio.wait_for(queued.wait(), 2)
        assert not snapshots  # Both handlers are waiting for the first wire generation.
        if terminal == "complete":
            finish_first.set()
            release_cleanup.set()
            expected_old = "first part rest"
        else:
            fields = ({"stage": "max_duration"} if terminal == "response.timeout"
                      else {"heard_text": "first"})
            socket.enqueue(terminal, response_id=first.response_id, **fields)
            await asyncio.wait_for(cleanup_started.wait(), 2)
            expected_old = "first part" if terminal == "response.timeout" else "first"
        expected_done = 3 if terminal == "complete" else 2
        await _wait_for_decline_event(socket, lambda: sum(
            event["type"] == "response.done" for event in socket.frames
        ) == expected_done)
        previous = ["old question", expected_old]
        assert texts(snapshots["second question"]) == previous
        assert texts(snapshots["future question"]) == previous + [
            "second question", "second answer"
        ]
        if terminal != "complete":
            assert not first.task.done()  # History was corrected before old cleanup finished.
    finally:
        finish_first.set()
        release_cleanup.set()
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.parametrize("first_kind", ["user.message", "user.no_input"])
async def test_duplicate_no_input_cannot_teardown_an_active_conversation_or_worker(first_kind):
    async def handler(request, _context, _signal):
        yield {"type": "response.output_text.delta", "delta": request["input"]}

    app = create_app(handler=handler, configure_observability=None)
    runtime = app.state.voice_runtime
    socket = DeclineHostSocket()
    _enqueue_decline_start(socket)
    fields = {"content": [{"type": "input_text", "text": "hello"}]} if (
        first_kind == "user.message"
    ) else {"count": 1}
    socket.enqueue(first_kind, item_id="in_claimed", **fields)
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await _wait_for_decline_event(socket, lambda: any(
            frame["type"] == "response.done" for frame in socket.frames
        ))
        session = Session._current(socket)
        conversation = runtime._conversations[session]
        business_task = conversation.task_store.create_task("cooperative worker")
        business_task.status = TaskStatus.RUNNING
        worker = asyncio.create_task(business_task.cancel_event.wait())
        conversation.background_tasks.add(worker)
        worker.add_done_callback(conversation.background_tasks.discard)
        socket.enqueue("user.no_input", item_id="in_claimed", count=3)
        socket.enqueue("user.message", item_id="in_next",
                       content=[{"type": "input_text", "text": "next"}])
        await _wait_for_decline_event(socket, lambda: sum(
            frame["type"] == "response.done" for frame in socket.frames
        ) == 2)
        assert runtime._conversations[session] is conversation
        assert runtime._store.active(session) is not None
        assert not worker.done()
        assert not any(frame["type"] == "end_call" for frame in socket.frames)
        socket.enqueue("user.no_input", item_id="in_end", count=3)
        await _wait_for_decline_event(socket, lambda: any(
            frame["type"] == "end_call" for frame in socket.frames
        ))
        await asyncio.wait_for(asyncio.gather(worker, return_exceptions=True), 2)
        assert session not in runtime._conversations
    finally:
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()
