# Copyright (c) Microsoft. All rights reserved.

"""Delivery is a successful CE send, not producing text or giving it to the Router."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from azure.ai.agentserver.invocations.voice import Session
from test_voice_runtime import (
    DeclineHostSocket,
    _enqueue_decline_start,
    _wait_for_decline_event,
)

from delivery import ConversationTaskStore
from task_store import TaskStatus
from voice_runtime import create_app


def texts(history):
    return [part["text"] for item in history for part in item["content"]]


@pytest.mark.parametrize("partial", [False, True])
async def test_history_contains_only_successfully_sent_text_after_timeout(partial):
    blocked = asyncio.Event()
    histories = []

    async def handler(request, context, _signal):
        if request["input"] == "first":
            if partial:
                yield {"type": "response.output_text.delta", "delta": "SENT"}
            yield {"type": "response.output_text.delta", "delta": "NEVER TRANSMITTED"}
        else:
            histories.append(await context.get_history())
            yield {"type": "response.output_text.delta", "delta": "second answer"}

    class Socket(DeclineHostSocket):
        async def send_text(self, text):
            event = json.loads(text)
            if (event["type"] == "response.output_text.delta"
                    and event["delta"] == "NEVER TRANSMITTED"):
                blocked.set()
                await asyncio.Future()
            await super().send_text(text)

    app = create_app(handler=handler, configure_observability=None)
    runtime, socket = app.state.voice_runtime, Socket()
    _enqueue_decline_start(socket)
    socket.enqueue("user.message", item_id="in_first",
                   content=[{"type": "input_text", "text": "first"}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(blocked.wait(), 2)
        session = Session._current(socket)
        first = next(iter(runtime._store.active(session).responses.values()))
        socket.enqueue("response.timeout", response_id=first.response_id,
                       stage="idle" if partial else "first_output")
        socket.enqueue("user.message", item_id="in_second",
                       content=[{"type": "input_text", "text": "second"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        assert texts(histories[0]) == ["first", *(["SENT"] if partial else [])]
        assert "NEVER TRANSMITTED" not in texts(runtime._conversations[session].history)
    finally:
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


def test_result_reservation_is_exclusive_reversible_and_requires_explicit_emission():
    store = ConversationTaskStore()
    task = store.create_task("work")
    task.result, task.status = "complete result", TaskStatus.COMPLETED
    assert store.reserve_completed("r_first") == [task]
    assert task.status is TaskStatus.COMPLETED
    assert store.reserve_completed("r_second") == []
    store.release_delivery("r_first")
    assert store.reserve_completed("r_second") == [task]
    store.commit_delivery("r_second")
    assert task.status is TaskStatus.COMPLETED
    assert store.reserve_completed("r_third") == [task]
    assert store.reserve_result("r_third", task)  # A direct-read path may own it already.
    store.record_emitted("r_third", [task.task_id])
    store.commit_delivery("r_third")
    assert task.status is TaskStatus.DELIVERED
    assert not store._delivery_owners


@pytest.fixture
def logic(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/test")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-model")
    import agent_logic

    return agent_logic


async def setup_app(logic, monkeypatch, router):
    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    monkeypatch.setattr(logic, "_TASK_POLL_INTERVAL", 0.001)
    app = create_app(handler=logic.handler, configure_observability=None)
    ready = asyncio.Event()
    original_start = app._voice_callbacks["session.start"]

    async def start(session, event):
        await original_start(session, event)
        ready.set()

    app._voice_callbacks["session.start"] = start
    socket = DeclineHostSocket()
    _enqueue_decline_start(socket)
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    await asyncio.wait_for(ready.wait(), 2)
    session = Session._current(socket)
    return app.state.voice_runtime, socket, connection, session


async def stop_app(runtime, socket, connection):
    socket.enqueue("session.end", reason="test_complete")
    await asyncio.wait_for(connection, 2)
    await runtime.close()


async def settle_responses(runtime, session):
    # Seeing bytes in the socket double precedes the SDK send coroutine returning.
    tasks = [operation.task for operation in runtime._store.active(session).responses.values()]
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 2)


def reply(text, *task_ids):
    return SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
        type="function_call", name="respond_directly",
        arguments={"message": text, "delivered_task_ids": list(task_ids)}
    ))


async def test_router_failure_rolls_back_result_for_next_turn(logic, monkeypatch):
    calls = []

    async def router(*args, **_kwargs):
        calls.append(args[3])
        if len(calls) == 1:
            raise RuntimeError("synthetic router failure")
        yield reply("RESULT", task.task_id)

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    task = runtime._conversations[session].task_store.create_task("work")
    task.result, task.status = "RESULT", TaskStatus.COMPLETED
    try:
        socket.enqueue("user.message", item_id="in_first",
                       content=[{"type": "input_text", "text": "first"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "error" for event in socket.frames
        ))
        assert task.status is TaskStatus.COMPLETED
        socket.enqueue("user.message", item_id="in_retry",
                       content=[{"type": "input_text", "text": "retry"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert task.status is TaskStatus.DELIVERED
        assert all("Recently completed" in str(items) for items in calls)
        assert not runtime._conversations[session].task_store._delivery_owners
    finally:
        await stop_app(runtime, socket, connection)


@pytest.mark.parametrize("running", [False, True])
@pytest.mark.parametrize("control", ["response.timeout", "user.barge_in"])
async def test_result_delivery_interruption_releases_claim_for_retry(
    logic, monkeypatch, running, control
):
    calls = []
    polling = asyncio.Event()

    async def sleep(delay):
        polling.set()
        await asyncio.sleep(delay)

    monkeypatch.setattr(logic, "asyncio", SimpleNamespace(**(vars(asyncio) | {"sleep": sleep})))

    async def router(*args, **_kwargs):
        calls.append(args[3])
        if running and len(calls) == 1:
            yield reply("ack")
        else:
            yield reply("RESULT", task.task_id)

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    task = runtime._conversations[session].task_store.create_task("work")
    task.status = TaskStatus.RUNNING if running else TaskStatus.COMPLETED
    task.result = "RESULT"
    blocked = asyncio.Event()
    original_send = socket.send_text

    async def send(text):
        event = json.loads(text)
        if (event["type"] == "response.output_text.delta" and event["delta"] == "RESULT"
                and not blocked.is_set()):
            blocked.set()
            await asyncio.Future()
        await original_send(text)

    socket.send_text = send
    try:
        socket.enqueue("user.message", item_id="in_first",
                       content=[{"type": "input_text", "text": "first"}])
        if running:
            await asyncio.wait_for(polling.wait(), 2)
            task.status = TaskStatus.COMPLETED
        await asyncio.wait_for(blocked.wait(), 2)
        assert task.status is TaskStatus.COMPLETED
        first = next(iter(runtime._store.active(session).responses.values()))
        fields = ({"stage": "idle" if running else "first_output"}
                  if control == "response.timeout" else {"heard_text": "ack" if running else ""})
        socket.enqueue(control, response_id=first.response_id, **fields)
        socket.enqueue("user.message", item_id="in_retry",
                       content=[{"type": "input_text", "text": "retry"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert task.status is TaskStatus.DELIVERED
        assert "Recently completed" in str(calls[-1])
        assert [event["delta"] for event in socket.frames
                if event["type"] == "response.output_text.delta"].count("RESULT") == 1
    finally:
        await stop_app(runtime, socket, connection)


@pytest.mark.parametrize("boundary", [
    "response.output_text.delta", "response.output_text.done", "response.done", "finalization"
])
async def test_failed_delivery_boundary_keeps_result_retryable(logic, monkeypatch, boundary):
    async def router(*_args, **_kwargs):
        yield reply("RESULT", task.task_id)

    if boundary == "finalization":
        original_handler = logic.handler

        async def handler(request, context, signal):
            async for event in original_handler(request, context, signal):
                yield event
            if request["input"] == "first":
                raise RuntimeError("synthetic finalization failure")

        monkeypatch.setattr(logic, "handler", handler)
    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    task = runtime._conversations[session].task_store.create_task("work")
    task.result, task.status = "RESULT", TaskStatus.COMPLETED
    original_send, failed = socket.send_text, False

    async def send(text):
        nonlocal failed
        if json.loads(text)["type"] == boundary and not failed:
            failed = True
            raise RuntimeError("synthetic send failure")
        await original_send(text)

    socket.send_text = send
    try:
        socket.enqueue("user.message", item_id="in_first",
                       content=[{"type": "input_text", "text": "first"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "error" for event in socket.frames
        ))
        assert task.status is TaskStatus.COMPLETED
        assert not runtime._conversations[session].task_store._delivery_owners
        socket.enqueue("user.message", item_id="in_retry",
                       content=[{"type": "input_text", "text": "retry"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert task.status is TaskStatus.DELIVERED
    finally:
        await stop_app(runtime, socket, connection)


@pytest.mark.parametrize("status", [None, TaskStatus.COMPLETED, TaskStatus.FAILED])
async def test_failed_cancel_is_not_acknowledged_as_success(logic, monkeypatch, status):
    async def router(*_args, **_kwargs):
        yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
            type="function_call", name="cancel_task",
            arguments={"task_id": "latest", "ack_message": "Cancelled."},
        ))

    runtime, socket, connection, _session = await setup_app(logic, monkeypatch, router)
    if status is not None:
        runtime._conversations[_session].task_store.create_task("old work").status = status
    try:
        socket.enqueue("user.message", item_id="in_cancel",
                       content=[{"type": "input_text", "text": "cancel"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        assert "".join(event.get("delta", "") for event in socket.frames) == (
            "There is no running task to cancel."
        )
    finally:
        await stop_app(runtime, socket, connection)


@pytest.mark.parametrize("message", ["All circuits are healthy.", "所有线路均正常。"])
async def test_paraphrased_or_translated_result_is_not_reoffered(logic, monkeypatch, message):
    calls = []

    async def router(*args, **_kwargs):
        calls.append(args[3])
        if len(calls) == 1:
            assert task.task_id in str(args[3])
            yield reply(message, task.task_id)
        else:
            yield reply("You're welcome.")

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    task = runtime._conversations[session].task_store.create_task("check circuits")
    task.result = "Circuit A is operational. Circuit B is operational. No faults were detected."
    task.status = TaskStatus.COMPLETED
    try:
        for index, text in enumerate(["result?", "Thanks"]):
            socket.enqueue("user.message", item_id=f"in_{index}",
                           content=[{"type": "input_text", "text": text}])
            await _wait_for_decline_event(socket, lambda expected=index + 1: sum(
                event["type"] == "response.done" for event in socket.frames
            ) == expected)
            await settle_responses(runtime, session)
            assert task.status is TaskStatus.DELIVERED
        assert "Recently completed" not in str(calls[1])
        assert "Recently delivered" in str(calls[1])
    finally:
        await stop_app(runtime, socket, connection)


async def test_substring_collision_does_not_consume_an_omitted_result(logic, monkeypatch):
    async def router(*_args, **_kwargs):
        yield reply("The second result is 10.", second.task_id)

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    store = runtime._conversations[session].task_store
    first, second = store.create_task("first"), store.create_task("second")
    first.result, second.result = "1", "10"
    first.status = second.status = TaskStatus.COMPLETED
    try:
        socket.enqueue("user.message", item_id="in_results",
                       content=[{"type": "input_text", "text": "results?"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert second.status is TaskStatus.DELIVERED
        assert first.status is TaskStatus.COMPLETED
        assert store.reserve_completed("r_next") == [first]
    finally:
        await stop_app(runtime, socket, connection)


@pytest.mark.parametrize("tool", ["check_task_status", "get_task_result"])
@pytest.mark.parametrize("completed_before_router", [False, True])
async def test_direct_result_paths_reserve_before_emission(
    logic, monkeypatch, tool, completed_before_router
):
    async def router(*_args, **_kwargs):
        # A Worker finishes after the entry scan, during model I/O.
        await asyncio.sleep(0)
        task.result, task.status = "RESULT", TaskStatus.COMPLETED
        yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
            type="function_call", name=tool,
            arguments={"task_id": "latest", "ack_message": "Ready."},
        ))

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    store = runtime._conversations[session].task_store
    task = store.create_task("work")
    task.result = "RESULT"
    task.status = TaskStatus.COMPLETED if completed_before_router else TaskStatus.RUNNING
    try:
        socket.enqueue("user.message", item_id="in_result",
                       content=[{"type": "input_text", "text": "result?"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert "RESULT" in "".join(event.get("delta", "") for event in socket.frames)
        assert task.status is TaskStatus.DELIVERED
        assert store.reserve_completed("r_next") == []
    finally:
        await stop_app(runtime, socket, connection)


def test_emission_cannot_claim_another_responses_result():
    store = ConversationTaskStore()
    task = store.create_task("work")
    task.result, task.status = "RESULT", TaskStatus.COMPLETED
    store.reserve_completed("r_owner")
    with pytest.raises(ValueError, match="owned reservation"):
        store.record_emitted("r_other", [task.task_id])
    store.commit_delivery("r_other")
    assert task.status is TaskStatus.COMPLETED


def test_released_emission_is_not_committed_by_a_later_response():
    store = ConversationTaskStore()
    task = store.create_task("work")
    task.result, task.status = "RESULT", TaskStatus.COMPLETED
    store.reserve_completed("r_first")
    store.record_emitted("r_first", [task.task_id])
    store.release_delivery("r_first")
    store.reserve_completed("r_second")
    store.commit_delivery("r_first")
    store.commit_delivery("r_second")
    assert task.status is TaskStatus.COMPLETED
    assert not store._emitted_results


@pytest.mark.parametrize("completion_point", ["router", "ack_send"])
async def test_result_finished_during_routing_or_ack_is_delivered_this_turn(
    logic, monkeypatch, completion_point
):
    async def router(*_args, **_kwargs):
        await asyncio.sleep(0)
        if completion_point == "router":
            task.status = TaskStatus.COMPLETED
        yield reply("Ready.")  # The Router did not have this result in its snapshot.

    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    task = runtime._conversations[session].task_store.create_task("work")
    task.status, task.result = TaskStatus.RUNNING, "RESULT"
    original_send = socket.send_text

    async def send(text):
        if completion_point == "ack_send" and json.loads(text).get("delta") == "Ready.":
            task.status = TaskStatus.COMPLETED
        await original_send(text)

    socket.send_text = send
    try:
        socket.enqueue("user.message", item_id="in_work",
                       content=[{"type": "input_text", "text": "status?"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert "".join(event.get("delta", "") for event in socket.frames) == "Ready.\n\nRESULT"
        assert task.status is TaskStatus.DELIVERED
    finally:
        await stop_app(runtime, socket, connection)


async def test_new_worker_finishing_during_ack_is_delivered_this_turn(logic, monkeypatch):
    finished = asyncio.Event()

    async def router(*_args, **_kwargs):
        yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
            type="function_call", name="start_task",
            arguments={"request_summary": "work", "ack_message": "On it."},
        ))

    async def worker(task, *_args):
        task.result, task.status = "RESULT", TaskStatus.COMPLETED
        finished.set()

    monkeypatch.setattr(logic, "run_worker", worker)
    runtime, socket, connection, session = await setup_app(logic, monkeypatch, router)
    original_send = socket.send_text

    async def send(text):
        if json.loads(text).get("delta") == "On it.":
            await finished.wait()
        await original_send(text)

    socket.send_text = send
    try:
        socket.enqueue("user.message", item_id="in_new_work",
                       content=[{"type": "input_text", "text": "work"}])
        await _wait_for_decline_event(socket, lambda: any(
            event["type"] == "response.done" for event in socket.frames
        ))
        await settle_responses(runtime, session)
        assert "".join(event.get("delta", "") for event in socket.frames) == "On it.\n\nRESULT"
        task = runtime._conversations[session].task_store.get("latest")
        assert task.status is TaskStatus.DELIVERED
    finally:
        await stop_app(runtime, socket, connection)
