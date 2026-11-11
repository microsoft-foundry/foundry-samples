"""Delivery replay, all spoken history, and bounded connection-owned task data."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    ResponseDone,
    ResponseOutputTextDelta,
    ResponseOutputTextDone,
)
from starlette.testclient import TestClient
from test_conversation_engine import (
    Chat,
    RecordingSession,
    Responses,
    answer,
    frame,
    output,
    send,
    start,
    tool,
    until,
)

from agent_logic import Conversation, ForegroundBackgroundAgent, Turn
from conversation_runtime import ConversationRuntime, HistorySession, create_app
from state import SessionState
from task_store import TaskStatus, TaskStore
from worker_agent import run_worker


@pytest.mark.parametrize(
    "replay_text",
    ["Use OS2 on panel 1.", "在一号面板使用 OS2。"],
    ids=["repeat", "translate"],
)
def test_delivered_result_can_be_replayed_then_unknown_ids_are_rejected(replay_text: str) -> None:
    async def replay(kwargs: dict) -> Any:
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        task = conversation.tasks.get("latest")
        assert task.status is TaskStatus.DELIVERED
        return tool("respond_directly", message=replay_text, delivered_task_ids=[task.task_id])

    chat = Chat(
        tool("start_task", request_summary="Find panels", ack_message="Checking."),
        replay,
        tool("respond_directly", message="Unknown result", delivered_task_ids=["unknown"]),
        tool("respond_directly", message="You're welcome."),
    )
    responses = Responses(answer("Use OS2 on panel 1."))
    app = create_app(
        ForegroundBackgroundAgent(chat, responses, "test"),
        configure_observability=None,
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_first", "Find panels")
        assert output(until(ws)) == "Checking.\n\nUse OS2 on panel 1."
        send(ws, "in_repeat", "Repeat or translate that result")
        repeated = []
        while True:
            item = ws.receive_json()
            repeated.append(item)
            if item["type"] in ("response.done", "error"):
                break
        assert repeated[-1]["type"] == "response.done"
        assert output(repeated) == replay_text
        assert repeated[0]["in_reply_to"] == ["in_repeat"]
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        assert conversation.tasks.get("latest").status is TaskStatus.DELIVERED
        send(ws, "in_unknown", "An unknown result")
        rejected = until(ws, "error")
        assert not output(rejected)
        assert not any(item["type"] == "response.done" for item in rejected)
        send(ws, "in_thanks", "Thanks")
        assert output(until(ws)) == "You're welcome."
    assert len(responses.requests) == 1


@pytest.mark.parametrize("status", [TaskStatus.COMPLETED, TaskStatus.DELIVERED])
async def test_failed_result_send_never_rolls_back_or_advances_delivery(status: TaskStatus) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status, task.result = status, "Panel result"
    chat = Chat(tool("respond_directly", message="Summary", delivered_task_ids=[task.task_id]))
    turn = Turn("r_replay")
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    assert (
        "".join([part async for part in agent.respond(conversation, turn, "Repeat")]) == "Summary"
    )
    state = SessionState()
    state.try_begin_start()
    state.activate()
    with pytest.raises(RuntimeError):
        await HistorySession(RecordingSession(fail=True), state, conversation, turn).send(
            ResponseDone(response_id=turn.response_id)
        )
    assert task.status is status
    await HistorySession(RecordingSession(), state, conversation, turn).send(
        ResponseDone(response_id=turn.response_id)
    )
    assert task.status is TaskStatus.DELIVERED


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("prior_turn", [False, True])
def test_idle_reminder_is_recorded_once_and_duplicate_input_is_ignored(
    count: int,
    prior_turn: bool,
) -> None:
    steps = [tool("respond_directly", message="Welcome.")] if prior_turn else []
    chat = Chat(*steps, tool("respond_directly", message="Thanks for confirming."))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"),
        configure_observability=None,
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        if prior_turn:
            send(ws, "in_prior", "Hello")
            until(ws)
        idle = frame("user.no_input", item_id="in_idle", count=count)
        ws.send_json(idle)
        reminder = until(ws)
        assert not output(reminder)
        assert [
            item["text"] for item in reminder if item["type"] == "response.output_text.done"
        ] == ["Are you still there?"]
        assert reminder[0]["in_reply_to"] == ["in_idle"]
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        assert sum(entry.content == "Are you still there?" for entry in conversation.history) == 1
        ws.send_json(idle)
        send(ws, "in_yes", "Yes, I am still here.")
        reply = until(ws)
        assert reply[0]["in_reply_to"] == ["in_yes"]
        assert output(reply) == "Thanks for confirming."
        assert {"role": "assistant", "content": "Are you still there?"} in chat.requests[-1][
            "messages"
        ]


@pytest.mark.parametrize("event_kind", ["user.barge_in", "response.cancelled"])
def test_reminder_playback_correction_is_used_by_the_router(event_kind: str) -> None:
    chat = Chat(tool("respond_directly", message="Thanks."))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"),
        configure_observability=None,
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        ws.send_json(frame("user.no_input", item_id="in_idle", count=1))
        reminder = until(ws)
        ws.send_json(
            frame(event_kind, response_id=reminder[0]["response_id"], heard_text="Are you")
        )
        send(ws, "in_yes", "Yes")
        until(ws)
    messages = chat.requests[0]["messages"]
    assert {"role": "assistant", "content": "Are you"} in messages
    assert "Are you still there?" not in repr(messages)


@pytest.mark.parametrize("streaming", [False, True])
async def test_text_done_records_nonstreaming_text_without_duplicating_deltas(
    streaming: bool,
) -> None:
    conversation = Conversation()
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, Turn("r_text"))
    if streaming:
        for delta in ["Are you ", "still there?"]:
            await session.send(
                ResponseOutputTextDelta(response_id="r_text", item_id="out", delta=delta)
            )
    await session.send(
        ResponseOutputTextDone(
            response_id="r_text",
            item_id="out",
            text="Are you still there?",
        )
    )
    assert [(entry.response_id, entry.content) for entry in conversation.history] == [
        ("r_text", "Are you still there?")
    ]


@pytest.mark.parametrize("callback", ["on_user_barge_in", "on_response_cancelled"])
@pytest.mark.parametrize("heard_text", ["Are you", ""], ids=["heard-prefix", "unheard"])
async def test_cancellation_during_first_nonstreaming_send_retains_heard_text(
    callback: str,
    heard_text: str,
) -> None:
    entered, finished, gate = asyncio.Event(), asyncio.Event(), asyncio.Event()
    sent = []

    class GatedSession(RecordingSession):
        async def send(self, message: Any) -> None:
            if isinstance(message, ResponseOutputTextDone) and not entered.is_set():
                entered.set()
                await gate.wait()
            sent.append(message)
            if isinstance(message, ResponseDone):
                finished.set()

    chat = Chat(tool("respond_directly", message="Replacement"))
    runtime = ConversationRuntime(ForegroundBackgroundAgent(chat, Responses(), "test"))
    session = GatedSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    try:
        await runtime.on_user_no_input(session, SimpleNamespace(item_id="in_idle", count=1))
        await asyncio.wait_for(entered.wait(), 1)
        response_id = next(iter(state.responses))
        await getattr(runtime, callback)(
            session,
            SimpleNamespace(response_id=response_id, heard_text=heard_text),
        )
        await runtime.on_user_message(
            session,
            SimpleNamespace(item_id="in_yes", content=[InputTextPart(text="Yes")]),
        )
        await asyncio.wait_for(finished.wait(), 1)
        assistants = [
            item["content"] for item in chat.requests[0]["messages"] if item["role"] == "assistant"
        ]
        assert assistants == ([heard_text] if heard_text else [])
        assert "Are you still there?" not in repr(chat.requests[0]["messages"])
        assert not any(
            isinstance(item, ResponseDone) and item.response_id == response_id for item in sent
        )
    finally:
        gate.set()
        await runtime.close()


async def test_failed_nonstreaming_send_does_not_enter_history_and_next_turn_works() -> None:
    failed, finished = asyncio.Event(), asyncio.Event()

    class FailOnce(RecordingSession):
        async def send(self, message: Any) -> None:
            if isinstance(message, ResponseOutputTextDone) and not failed.is_set():
                failed.set()
                raise RuntimeError("Injected send failure")
            if isinstance(message, ResponseDone):
                finished.set()

    chat = Chat(tool("respond_directly", message="Next reply"))
    runtime = ConversationRuntime(ForegroundBackgroundAgent(chat, Responses(), "test"))
    session = FailOnce()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    try:
        await runtime.on_user_no_input(session, SimpleNamespace(item_id="in_idle", count=1))
        await asyncio.wait_for(failed.wait(), 1)
        await runtime.on_user_message(
            session,
            SimpleNamespace(item_id="in_next", content=[InputTextPart(text="Next")]),
        )
        await asyncio.wait_for(finished.wait(), 1)
        assert "Are you still there?" not in repr(chat.requests[0]["messages"])
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "status",
    [
        TaskStatus.COMPLETED,
        TaskStatus.DELIVERED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ],
)
def test_all_terminal_results_expire_without_expiring_an_active_worker(status: TaskStatus) -> None:
    store = TaskStore()
    active = store.create_task("Active")
    active.status, active.created_at = TaskStatus.RUNNING, time.time() - 86400
    expired = store.create_task("Expired")
    expired.status, expired.finished_at = status, time.time() - 301
    store.cleanup()
    assert store.get(expired.task_id) is None
    assert store.get("latest") is None
    assert store.get(active.task_id) is active
    assert not active.cancel_event.is_set()


def test_capacity_evicts_oldest_terminal_result_but_never_marks_it_delivered() -> None:
    store = TaskStore()
    tasks = []
    now = time.time()
    for index in range(16):
        task = store.create_task(str(index))
        task.status, task.result, task.finished_at = (
            TaskStatus.COMPLETED,
            "Result",
            now - 16 + index,
        )
        tasks.append(task)
    new = store.create_task("New work")
    assert store.get(tasks[0].task_id) is None
    assert tasks[0].status is TaskStatus.COMPLETED
    assert all(store.get(task.task_id) is task for task in tasks[1:])
    assert len(store.completed_tasks()) == 15
    assert store.get("latest") is new


def test_capacity_does_not_evict_active_tasks_and_failed_admission_can_retry() -> None:
    store = TaskStore()
    tasks = [store.create_task(str(index)) for index in range(16)]
    with pytest.raises(ValueError):
        store.create_task("Too many active tasks")
    assert all(store.get(task.task_id) is task for task in tasks)
    tasks[0].status, tasks[0].finished_at = TaskStatus.COMPLETED, time.time()
    new = store.create_task("Retry")
    assert store.get(tasks[0].task_id) is None
    assert len(store.active_tasks()) == 16
    assert store.get("latest") is new


def test_oversized_query_rejection_does_not_evict_an_existing_result() -> None:
    store = TaskStore()
    tasks = []
    for index in range(16):
        task = store.create_task(str(index))
        task.status, task.finished_at = TaskStatus.COMPLETED, time.time()
        tasks.append(task)
    with pytest.raises(ValueError):
        store.create_task("Q" * 8001)
    assert all(store.get(task.task_id) is task for task in tasks)
    assert store.get("latest") is tasks[-1]
    new = store.create_task("Q" * 8000)
    assert store.get("latest") is new


@pytest.mark.parametrize("size", [8000, 8001], ids=["at-limit", "over-limit"])
@pytest.mark.parametrize("cancelled", [False, True], ids=["normal", "cancelled-inflight"])
async def test_worker_result_size_is_checked_on_every_final_answer(
    size: int, cancelled: bool
) -> None:
    loop = asyncio.get_running_loop()
    task = TaskStore().create_task("Find panels")

    def model() -> Any:
        if cancelled:
            loop.call_soon_threadsafe(task.cancel_event.set)
        return answer("界" * size)

    await run_worker(task, [], Responses(model), "test")
    if size == 8000:
        assert task.status is TaskStatus.COMPLETED
        assert task.result == "界" * size
    else:
        assert task.status is TaskStatus.FAILED
        assert len(task.result) <= 8000
        assert "界" not in task.result
    assert task.finished_at is not None


async def test_task_context_is_bounded_and_full_retained_result_can_still_be_fetched() -> None:
    conversation = Conversation()
    for index in range(16):
        task = conversation.tasks.create_task(f"Query {index}")
        task.status, task.result, task.finished_at = TaskStatus.COMPLETED, "界" * 8000, time.time()
    latest = conversation.tasks.get("latest")
    chat = Chat(tool("get_task_result", task_id="latest"))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_full_result")
    assert (
        "".join([part async for part in agent.respond(conversation, turn, "Read latest")])
        == latest.result
    )
    contexts = [
        item["content"] for item in chat.requests[0]["messages"][1:] if item["role"] == "system"
    ]
    assert len(contexts) == 1 and len(contexts[0]) <= 8000
    assert "get_task_result" in contexts[0]
    assert "界" not in contexts[0]  # Omit result bodies instead of presenting partial answers.
    assert turn.delivered_task_ids == {latest.task_id}
    assert latest.status is TaskStatus.COMPLETED


@pytest.mark.parametrize("evicted", [False, True], ids=["expired", "evicted"])
async def test_unavailable_result_is_explicit_and_never_redirects_to_an_older_task(
    evicted: bool,
) -> None:
    conversation = Conversation()
    target = conversation.tasks.create_task("Target")
    target.status, target.result, target.finished_at = (
        TaskStatus.COMPLETED,
        "Old result",
        time.time() - 301,
    )
    if evicted:
        target.finished_at = time.time() - 20
        for index in range(16):
            task = conversation.tasks.create_task(str(index))
            task.status, task.result, task.finished_at = (
                TaskStatus.COMPLETED,
                "Other result",
                time.time(),
            )
    chat = Chat(tool("get_task_result", task_id=target.task_id))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_unavailable")
    text = "".join([part async for part in agent.respond(conversation, turn, "Read target")])
    assert "expired" in text.lower() and "evicted" in text.lower()
    assert "Old result" not in text and "Other result" not in text
    assert not turn.delivered_task_ids


def test_terminal_retention_boundary_is_measured_from_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import task_store

    store = TaskStore()
    tasks = [store.create_task(str(index)) for index in range(3)]
    for task, finished_at in zip(tasks, [700.001, 700.0, 699.999], strict=True):
        task.status, task.created_at, task.finished_at = TaskStatus.COMPLETED, 0, finished_at
    monkeypatch.setattr(task_store.time, "time", lambda: 1000.0)
    store.cleanup()
    assert store.get(tasks[0].task_id) is tasks[0]
    assert store.get(tasks[1].task_id) is tasks[1]
    assert store.get(tasks[2].task_id) is None
    assert store.get("latest") is None


async def test_small_task_context_keeps_complete_results() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status, task.result = TaskStatus.COMPLETED, "Use OS2 on panel 1."
    chat = Chat(tool("respond_directly", message=task.result, delivered_task_ids=[task.task_id]))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_small_context")
    assert (
        "".join([part async for part in agent.respond(conversation, turn, "Read result")])
        == task.result
    )
    assert task.result in repr(chat.requests[0]["messages"])
    assert "Result bodies omitted" not in repr(chat.requests[0]["messages"])
    assert turn.delivered_task_ids == {task.task_id}


@pytest.mark.parametrize("mixed_claim", [False, True], ids=["unseen-only", "visible-and-unseen"])
async def test_unseen_result_claim_is_rejected_atomically_then_can_be_retrieved(
    mixed_claim: bool,
) -> None:
    conversation = Conversation()
    visible = conversation.tasks.create_task("Earlier work")
    visible.status, visible.result = TaskStatus.COMPLETED, "Earlier result"
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING

    async def finish_and_report(kwargs: dict) -> Any:
        request = repr(kwargs["messages"])
        assert visible.result in request and "Panel result" not in request
        await asyncio.sleep(0)
        task.status, task.result, task.finished_at = (
            TaskStatus.COMPLETED,
            "Panel result",
            time.time(),
        )
        reported = [visible.task_id, task.task_id] if mixed_claim else [task.task_id]
        return tool("respond_directly", message="Still checking.", delivered_task_ids=reported)

    agent = ForegroundBackgroundAgent(
        Chat(finish_and_report, tool("get_task_result", task_id=task.task_id)), Responses(), "test"
    )
    turn = Turn("r_became_ready")
    with pytest.raises(ValueError):
        await anext(agent.respond(conversation, turn, "Status?"))
    assert not turn.delivered_task_ids
    assert task.status is visible.status is TaskStatus.COMPLETED
    assert all(entry.role == "user" for entry in conversation.history)
    retry = Turn("r_retrieved")
    assert (
        "".join([part async for part in agent.respond(conversation, retry, "Read the result")])
        == task.result
    )
    assert retry.delivered_task_ids == {task.task_id}
    assert task.status is TaskStatus.COMPLETED
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, retry)
    await session.send(
        ResponseOutputTextDelta(
            response_id=retry.response_id,
            item_id="out_result",
            delta=task.result,
        )
    )
    assert task.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=retry.response_id))
    assert conversation.history[-1].content == task.result
    assert task.status is TaskStatus.DELIVERED
    assert visible.status is TaskStatus.COMPLETED
