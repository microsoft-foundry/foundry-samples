"""Successful status speech is not delivery of the underlying Worker result."""

import json
import threading

import pytest
from azure.ai.agentserver.invocations.voice import ResponseDone, ResponseOutputTextDelta
from starlette.testclient import TestClient
from test_conversation_engine import (
    Chat,
    RecordingSession,
    Responses,
    answer,
    chat_reply,
    frame,
    output,
    presentation_reply,
    send,
    start,
    tool,
    until,
    wait_for_server,
)

from agent_logic import Conversation, ForegroundBackgroundAgent, Turn
from conversation_runtime import HistorySession, create_app
from state import SessionState
from task_store import TaskStatus


@pytest.mark.parametrize("route", ["get_task_result", "check_task_status"])
@pytest.mark.parametrize("timing", ["already-ready", "during-routing", "during-ack"])
@pytest.mark.parametrize("convey_result", [False, True], ids=["status-only", "summarized-result"])
async def test_delivery_requires_result_content_then_successful_terminal_send(
    route: str, timing: str, convey_result: bool
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find the panel specification")
    task.status = TaskStatus.RUNNING

    def finish():
        task.status, task.result = TaskStatus.COMPLETED, "Use OS2 on panel 1."

    if timing == "already-ready":
        finish()

    async def route_request(kwargs):
        if timing == "during-routing":
            finish()
        return tool(route, task_id=task.task_id, ack_message="Checking.")

    presented = "Panel 1 needs OS2." if convey_result else "Yes, it is ready."
    agent = ForegroundBackgroundAgent(
        Chat(
            route_request,
            presentation_reply(presented, result_conveyed=convey_result),
            tool("get_task_result", task_id=task.task_id),
            presentation_reply("一号面板使用 OS2。"),
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_status")
    request = (
        "Summarize the result" if convey_result
        else "Only tell me whether it is ready; do not read the result."
    )
    stream = agent.respond(conversation, turn, request)
    chunks = []
    if timing == "during-ack":
        chunks.append(await anext(stream))
        assert chunks == ["Checking."]
        finish()
    chunks.extend([part async for part in stream])
    assert turn.delivered_task_ids == ({task.task_id} if convey_result else set())
    assert "".join(chunks) == ("Checking.\n\n" if timing == "during-ack" else "") + presented
    assert task.result not in "".join(chunks)  # A literal-substring delivery oracle is invalid.
    assert task.status is TaskStatus.COMPLETED
    assert conversation.tasks.completed_tasks() == [task]
    assert not agent.workers and len(agent.chat.requests) == 2

    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, turn)
    for chunk in chunks:
        await session.send(
            ResponseOutputTextDelta(response_id=turn.response_id, item_id="out", delta=chunk)
        )
    assert task.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=turn.response_id))
    assert task.status is (TaskStatus.DELIVERED if convey_result else TaskStatus.COMPLETED)
    assert conversation.history[-1].content == "".join(chunks)

    # Continue after a successful status-only response: the actual result is still pending.
    # Also replay a delivered result: its state must stay delivered, not reopen.
    retry = Turn("r_read_result")
    text = "".join([s async for s in agent.respond(conversation, retry, "现在读出中文结果")])
    assert text == "一号面板使用 OS2。"
    assert retry.delivered_task_ids == (set() if convey_result else {task.task_id})
    retried = HistorySession(RecordingSession(), state, conversation, retry)
    await retried.send(
        ResponseOutputTextDelta(response_id=retry.response_id, item_id="out_retry", delta=text)
    )
    assert task.status is (TaskStatus.DELIVERED if convey_result else TaskStatus.COMPLETED)
    await retried.send(ResponseDone(response_id=retry.response_id))
    await retried.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED
    assert not conversation.tasks.completed_tasks()
    assert conversation.tasks.get(task.task_id) is task
    assert len(agent.chat.requests) == 4 and not agent.workers


@pytest.mark.parametrize("during_ack", [False, True], ids=["already-ready", "during-ack"])
@pytest.mark.parametrize(
    "payload",
    [
        {"message": "Yes, ready."},
        {"message": "Yes, ready.", "result_conveyed": "false"},
        {"message": "Yes, ready.", "result_conveyed": 1},
        {"message": "Yes, ready.", "result_conveyed": None},
        {"message": "", "result_conveyed": True},
        {"message": " \n", "result_conveyed": False},
        {"message": 123, "result_conveyed": True},
        ["Yes, ready.", True],
    ],
    ids=[
        "missing-claim", "string-claim", "integer-claim", "null-claim", "empty", "blank",
        "nontext", "not-object",
    ],
)
async def test_invalid_claim_never_changes_delivery_and_retry_can_commit(
    payload, during_ack
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING if during_ack else TaskStatus.COMPLETED
    task.result = "Use OS2 on panel 1."
    agent = ForegroundBackgroundAgent(
        Chat(
            tool("get_task_result", task_id=task.task_id, ack_message="Checking."),
            chat_reply(json.dumps(payload)),
            tool("get_task_result", task_id=task.task_id),
            presentation_reply("Panel 1 needs OS2."),
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_invalid_claim")
    stream = agent.respond(conversation, turn, "Read it")
    if during_ack:
        assert await anext(stream) == "Checking."
        task.status = TaskStatus.COMPLETED
    with pytest.raises(ValueError):
        await anext(stream)
    assert not turn.delivered_task_ids
    assert task.status is TaskStatus.COMPLETED and conversation.tasks.completed_tasks() == [task]
    assert all(entry.role == "user" for entry in conversation.history)
    assert not agent.workers
    retry = Turn("r_retry_claim")
    chunks = [s async for s in agent.respond(conversation, retry, "Read it again")]
    assert "".join(chunks) == "Panel 1 needs OS2."
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, retry)
    for chunk in chunks:
        await session.send(
            ResponseOutputTextDelta(response_id=retry.response_id, item_id="out", delta=chunk)
        )
    assert task.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED
    assert conversation.history[-1].content == "Panel 1 needs OS2."


@pytest.mark.parametrize("route", ["get_task_result", "check_task_status"])
@pytest.mark.parametrize("timing", ["already-ready", "during-ack"])
def test_real_sdk_status_only_preserves_pending_result_for_next_turn(route, timing) -> None:
    entered, release = threading.Event(), threading.Event()
    result = "Use OS2 on panel 1."

    def blocked_model():
        entered.set()
        assert release.wait(5)
        return answer(result)

    async def retrieve(kwargs):
        # Routing the next turn also synchronizes past the previous send continuation.
        assert task.status is TaskStatus.COMPLETED
        assert conversation.tasks.completed_tasks() == [task]
        assert any(
            f"Completed task {task.task_id}" in item["content"] and result in item["content"]
            for item in kwargs["messages"]
        )
        return tool("get_task_result", task_id=task.task_id)

    agent = ForegroundBackgroundAgent(
        Chat(
            tool("start_task", request_summary="Find panels", ack_message="Looking."),
            tool(route, task_id="latest", ack_message="Checking."),
            presentation_reply("Yes, it is ready.", result_conveyed=False),
            retrieve,
            presentation_reply("一号面板使用 OS2。"),
            tool("respond_directly", message="You're welcome."),
        ),
        Responses(blocked_model),
        "test",
    )
    app = create_app(agent, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        try:
            start(ws)
            send(ws, "in_start", "Find panels")
            initial = ws.receive_json()
            assert ws.receive_json()["delta"] == "Looking."
            assert entered.wait(2)
            conversation = next(iter(app.state.voice_runtime.conversations.values()))
            task = conversation.tasks.get("latest")
            ws.send_json(
                frame("user.barge_in", response_id=initial["response_id"], heard_text="Looking.")
            )
            if timing == "already-ready":
                release.set()
                wait_for_server(client, lambda: task.status is TaskStatus.COMPLETED)
            send(ws, "in_status", "Only say whether it is ready; do not read the result.")
            status_frames = [ws.receive_json()]
            assert status_frames[0]["in_reply_to"] == ["in_status"]
            if timing == "during-ack":
                status_frames.append(ws.receive_json())
                assert status_frames[-1]["delta"] == "Checking."
                release.set()
            status_frames += until(ws)
            assert output(status_frames) == (
                "Checking.\n\n" if timing == "during-ack" else ""
            ) + "Yes, it is ready."
            assert sum(f["type"] == "response.done" for f in status_frames) == 1
            assert result not in repr(status_frames)
            assert "result_conveyed" not in repr(status_frames)
            assert all(f["type"] != "error" for f in status_frames)

            send(ws, "in_result", "现在读出中文结果")
            result_frames = until(ws)
            assert result_frames[0]["in_reply_to"] == ["in_result"]
            assert output(result_frames) == "一号面板使用 OS2。"
            assert all(f["type"] != "error" for f in result_frames)
            wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
            assert conversation.history[-1].content == "一号面板使用 OS2。"
            assert any(
                entry.content.endswith("Yes, it is ready.") for entry in conversation.history
            )
            assert not conversation.tasks.completed_tasks()
            assert len(agent.responses.requests) == 1
            send(ws, "in_thanks", "Thanks")
            later = until(ws)
            assert output(later) == "You're welcome."
            assert all(f.get("response_id") != initial["response_id"] for f in later)
        finally:
            release.set()
    assert not agent.workers and not app.state.voice_runtime.conversations
    assert not app.state.voice_runtime._coordinator._detached_tasks


@pytest.mark.parametrize("fail_at", ["text", "terminal"])
@pytest.mark.parametrize("convey_result", [False, True], ids=["status-only", "result"])
async def test_failed_send_cannot_commit_presentation_and_next_turn_can_deliver(
    fail_at: str, convey_result: bool
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status, task.result = TaskStatus.COMPLETED, "Use OS2 on panel 1."
    text = "Panel 1 needs OS2." if convey_result else "Yes, it is ready."
    agent = ForegroundBackgroundAgent(
        Chat(
            tool("check_task_status", task_id=task.task_id),
            presentation_reply(text, result_conveyed=convey_result),
            tool("get_task_result", task_id=task.task_id),
            presentation_reply("一号面板使用 OS2。"),
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_failed_send")
    chunks = [s async for s in agent.respond(conversation, turn, "Status?")]
    state = SessionState()
    state.try_begin_start()
    state.activate()
    transport = RecordingSession(fail=fail_at == "text")
    session = HistorySession(transport, state, conversation, turn)
    with pytest.raises(RuntimeError):
        for chunk in chunks:
            await session.send(
                ResponseOutputTextDelta(response_id=turn.response_id, item_id="out", delta=chunk)
            )
        transport.fail = True
        await session.send(ResponseDone(response_id=turn.response_id))
    assert task.status is TaskStatus.COMPLETED and conversation.tasks.completed_tasks() == [task]
    assert [entry.content for entry in conversation.history if entry.role == "assistant"] == (
        [] if fail_at == "text" else [text]
    )
    assert not agent.workers
    retry = Turn("r_after_send_failure")
    chunks = [s async for s in agent.respond(conversation, retry, "现在读出中文结果")]
    assert "".join(chunks) == "一号面板使用 OS2。"
    retried = HistorySession(RecordingSession(), state, conversation, retry)
    for chunk in chunks:
        await retried.send(
            ResponseOutputTextDelta(response_id=retry.response_id, item_id="out", delta=chunk)
        )
    assert task.status is TaskStatus.COMPLETED
    await retried.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED and not conversation.tasks.completed_tasks()
