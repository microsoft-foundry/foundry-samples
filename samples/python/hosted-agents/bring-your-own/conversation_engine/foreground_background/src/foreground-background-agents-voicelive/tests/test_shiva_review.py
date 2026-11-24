"""Cancellation turns acknowledge only; retrieved results honor the current request."""

import asyncio
import json
import threading

import httpx
import pytest
from azure.ai.agentserver.invocations.voice import ResponseDone, ResponseOutputTextDelta
from openai import AsyncOpenAI
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


async def test_cancellation_turn_finishes_without_joining_worker() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING
    agent = ForegroundBackgroundAgent(
        Chat(tool("cancel_task", task_id="latest", ack_message="Stopping.")),
        Responses(),
        "test",
    )
    turn = Turn("r_cancel")
    stream = agent.respond(conversation, turn, "Stop the work")
    try:
        assert await anext(stream) == "Stopping."
        assert task.cancel_event.is_set()
        # A still-running Worker must not hold the cancellation response open.
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 1)
        assert task.status is TaskStatus.RUNNING
        assert not turn.delivered_task_ids
    finally:
        await stream.aclose()


@pytest.mark.parametrize("during", ["routing", "acknowledgment"])
async def test_cancel_turn_never_claims_result_that_wins_the_completion_race(during: str) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING

    async def cancel(kwargs):
        if during == "routing":
            task.status, task.result = TaskStatus.COMPLETED, "LATE ANSWER"
        return tool("cancel_task", task_id="latest", ack_message="Stopping.")

    agent = ForegroundBackgroundAgent(Chat(cancel), Responses(), "test")
    turn = Turn("r_cancel_race")
    stream = agent.respond(conversation, turn, "Cancel")
    first = await anext(stream)
    if during == "acknowledgment":
        assert first == "Stopping."
        task.status, task.result = TaskStatus.COMPLETED, "LATE ANSWER"
    spoken = first + "".join([part async for part in stream])
    assert "LATE ANSWER" not in spoken
    assert task.status is TaskStatus.COMPLETED
    assert not turn.delivered_task_ids


def test_real_sdk_cancel_does_not_deliver_late_worker_answer_and_next_turn_can_fetch() -> None:
    entered, release = threading.Event(), threading.Event()
    result = "LATE WORKER ANSWER"

    def blocked_model():
        entered.set()
        assert release.wait(5)
        return answer(result)

    agent = ForegroundBackgroundAgent(
        Chat(
            tool("start_task", request_summary="Find panels", ack_message="Looking."),
            tool("cancel_task", task_id="latest", ack_message="Stopping."),
            tool("get_task_result", task_id="latest"),
            presentation_reply("Retrieved late answer."),
        ),
        Responses(blocked_model),
        "test",
    )
    app = create_app(agent, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        try:
            start(ws)
            send(ws, "in_work", "Find panels")
            first = ws.receive_json()
            assert ws.receive_json()["delta"] == "Looking."
            assert entered.wait(2)
            ws.send_json(
                frame("user.barge_in", response_id=first["response_id"], heard_text="Looking.")
            )
            send(ws, "in_cancel", "Stop work")
            cancellation = [ws.receive_json(), ws.receive_json()]
            assert cancellation[-1]["delta"] == "Stopping."
            release.set()  # The accepted cancellation cannot abort this already-started call.
            cancellation += until(ws)
            assert output(cancellation) == "Stopping."
            assert sum(f["type"] == "response.done" for f in cancellation) == 1
            conversation = next(iter(app.state.voice_runtime.conversations.values()))
            task = conversation.tasks.get("latest")
            wait_for_server(client, lambda: task.status is TaskStatus.COMPLETED)
            assert task.cancel_event.is_set() and task.result == result
            assert conversation.history[-1].content == "Stopping."
            send(ws, "in_fetch", "Read the saved result")
            fetched = until(ws)
            assert output(fetched) == "Retrieved late answer."
            assert fetched[0]["in_reply_to"] == ["in_fetch"]
            assert all(f.get("response_id") != first["response_id"] for f in fetched)
            wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
            assert len(agent.responses.requests) == 1
        finally:
            release.set()
    assert not agent.workers


@pytest.mark.parametrize("status", [TaskStatus.COMPLETED, TaskStatus.DELIVERED])
@pytest.mark.parametrize(
    "user_request,presented,convey_result",
    [
        ("请把结果翻译成中文", "中文译文：保留最后一步。", True),
        ("Summarize the result", "Summary: retain the final step.", True),
        ("Is it ready? Do not read the result.", "Yes, it is ready.", False),
    ],
    ids=["translate", "summarize", "status-only"],
)
async def test_real_model_sdk_receives_full_result_and_current_request_before_presentation(
    status: TaskStatus,
    user_request: str,
    presented: str,
    convey_result: bool,
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = status
    task.result = "x" * (8000 - len("FINAL STEP")) + "FINAL STEP"
    requests = []
    selected = tool("get_task_result", task_id=task.task_id)

    def handle(http_request):
        data = json.loads(http_request.content)
        requests.append(data)
        if len(requests) == 1:
            assert "FINAL STEP" not in repr(data["messages"])
            assert "Result bodies omitted" in repr(data["messages"])
            return httpx.Response(200, json=selected.model_dump(mode="json"))
        assert len(requests) == 2  # There is no open-ended tool/presentation loop.
        assert data["tool_choice"] == "none"
        assert data["response_format"] == {"type": "json_object"}
        assert {"role": "user", "content": user_request} in data["messages"]
        result_message = data["messages"][-1]
        previous_call = data["messages"][-2]["tool_calls"][0]
        assert previous_call == selected.choices[0].message.tool_calls[0].model_dump(
            exclude_none=True
        )
        assert result_message["role"] == "tool"
        assert result_message["tool_call_id"] == previous_call["id"]
        payload = json.loads(result_message["content"])
        assert payload["task_id"] == task.task_id and payload["result"] == task.result
        return httpx.Response(
            200,
            json=presentation_reply(presented, result_conveyed=convey_result).model_dump(
                mode="json"
            ),
        )

    async with AsyncOpenAI(
        api_key="offline-test",
        base_url="https://offline.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    ) as client:
        agent = ForegroundBackgroundAgent(client.chat.completions, Responses(), "test")
        turn = Turn("r_present")
        chunks = [s async for s in agent.respond(conversation, turn, user_request)]
    assert len(requests) == 2
    assert "".join(chunks) == presented
    assert task.result not in "".join(chunks)
    assert task.status is status
    assert turn.delivered_task_ids == (
        {task.task_id} if status is TaskStatus.COMPLETED and convey_result else set()
    )
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, turn)
    for chunk in chunks:
        await session.send(
            ResponseOutputTextDelta(response_id=turn.response_id, item_id="out", delta=chunk)
        )
    assert task.status is status
    with pytest.raises(RuntimeError):
        await HistorySession(RecordingSession(fail=True), state, conversation, turn).send(
            ResponseDone(response_id=turn.response_id)
        )
    assert task.status is status
    await session.send(ResponseDone(response_id=turn.response_id))
    assert task.status is (TaskStatus.DELIVERED if convey_result else status)
    assert conversation.history[-1].content == presented


@pytest.mark.parametrize(
    "bad_reply",
    [
        chat_reply(""),
        chat_reply(" \n"),
        chat_reply("partial", finish_reason="length"),
        chat_reply("not an answer", refusal="Declined"),
        tool("start_task", request_summary="wrong"),
    ],
    ids=["empty", "blank", "incomplete", "refusal", "unexpected-tool"],
)
async def test_invalid_presentation_does_not_commit_and_can_be_retried(bad_reply) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status, task.result = TaskStatus.COMPLETED, "Full original result"
    agent = ForegroundBackgroundAgent(
        Chat(
            tool("get_task_result", task_id=task.task_id),
            bad_reply,
            tool("get_task_result", task_id=task.task_id),
            presentation_reply("Translated answer"),
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_bad")
    with pytest.raises(ValueError):
        await anext(agent.respond(conversation, turn, "Translate"))
    assert task.status is TaskStatus.COMPLETED and not turn.delivered_task_ids
    assert not agent.workers and len(conversation.tasks.completed_tasks()) == 1
    assert all(e.role == "user" for e in conversation.history)
    retry = Turn("r_retry")
    assert (
        "".join([s async for s in agent.respond(conversation, retry, "Translate again")])
        == "Translated answer"
    )
    assert retry.delivered_task_ids == {task.task_id}
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, retry)
    await session.send(
        ResponseOutputTextDelta(
            response_id=retry.response_id,
            item_id="out_retry",
            delta="Translated answer",
        )
    )
    assert task.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED
    assert conversation.history[-1].content == "Translated answer"


async def test_failed_cancel_ack_keeps_accepted_cancellation_and_allows_later_result_delivery() -> (
    None
):
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = TaskStatus.RUNNING
    agent = ForegroundBackgroundAgent(
        Chat(
            tool("cancel_task", task_id="latest", ack_message="Stopping."),
            tool("get_task_result", task_id="latest"),
            presentation_reply("Saved late result"),
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_failed_cancel_ack")
    stream = agent.respond(conversation, turn, "Cancel")
    state = SessionState()
    state.try_begin_start()
    state.activate()
    try:
        acknowledgment = await anext(stream)
        with pytest.raises(RuntimeError):
            await HistorySession(RecordingSession(fail=True), state, conversation, turn).send(
                ResponseOutputTextDelta(
                    response_id=turn.response_id, item_id="out_ack", delta=acknowledgment
                )
            )
    finally:
        await stream.aclose()
    assert task.cancel_event.is_set() and task.status is TaskStatus.RUNNING
    assert not turn.delivered_task_ids and all(e.role == "user" for e in conversation.history)
    task.status, task.result = TaskStatus.COMPLETED, "Saved late result"
    retry = Turn("r_after_cancel_send_failure")
    text = "".join([s async for s in agent.respond(conversation, retry, "Read the saved result")])
    assert text == task.result
    session = HistorySession(RecordingSession(), state, conversation, retry)
    await session.send(
        ResponseOutputTextDelta(response_id=retry.response_id, item_id="out_result", delta=text)
    )
    assert task.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED


@pytest.mark.parametrize("route", ["get_task_result", "check_task_status"])
async def test_result_ready_while_acknowledgment_streams_is_presented_once(route: str) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = TaskStatus.RUNNING

    async def present(kwargs):
        assert json.loads(kwargs["messages"][-1]["content"])["result"] == "Original procedure"
        assert {"role": "user", "content": "Translate the result"} in kwargs["messages"]
        return presentation_reply("Translated procedure")

    agent = ForegroundBackgroundAgent(
        Chat(
            tool(route, task_id=task.task_id, ack_message="Checking."),
            present,
        ),
        Responses(),
        "test",
    )
    turn = Turn("r_waiting")
    stream = agent.respond(conversation, turn, "Translate the result")
    assert await anext(stream) == "Checking."
    task.status, task.result = TaskStatus.COMPLETED, "Original procedure"
    assert "".join([s async for s in stream]) == "\n\nTranslated procedure"
    assert turn.delivered_task_ids == {task.task_id}
    assert task.status is TaskStatus.COMPLETED
    assert len(agent.chat.requests) == 2


async def test_unknown_cancel_does_not_cancel_other_work_and_matching_retry_can_cancel() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = TaskStatus.RUNNING
    agent = ForegroundBackgroundAgent(
        Chat(
            tool("cancel_task", task_id="unknown", ack_message="Stopping."),
            tool("cancel_task", task_id=task.task_id, ack_message="Stopping."),
        ),
        Responses(),
        "test",
    )
    first = Turn("r_unknown_cancel")
    assert "no matching" in "".join([s async for s in agent.respond(conversation, first, "Cancel")])
    assert not task.cancel_event.is_set() and task.status is TaskStatus.RUNNING
    assert not first.delivered_task_ids
    retry = Turn("r_matching_cancel")
    assert (
        "".join([s async for s in agent.respond(conversation, retry, "Cancel latest")])
        == "Stopping."
    )
    assert task.cancel_event.is_set() and task.status is TaskStatus.RUNNING
    assert not retry.delivered_task_ids


@pytest.mark.parametrize("interruption", ["provider-error", "response.timeout", "user.barge_in"])
def test_presentation_interruption_keeps_result_pending_and_replacement_can_translate(
    interruption: str,
) -> None:
    entered, cancelled = threading.Event(), threading.Event()

    async def interrupted_presentation(kwargs):
        assert json.loads(kwargs["messages"][-1]["content"])["result"] == "Original result"
        entered.set()
        if interruption == "provider-error":
            raise RuntimeError("PRIVATE_PROVIDER_DIAGNOSTIC")
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    agent = ForegroundBackgroundAgent(
        Chat(
            tool("respond_directly", message="Hello."),
            tool("get_task_result", task_id="latest"),
            interrupted_presentation,
            tool("get_task_result", task_id="latest"),
            presentation_reply("Translated result."),
            tool("respond_directly", message="Welcome."),
        ),
        Responses(),
        "test",
    )
    app = create_app(agent, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_setup", "Hello")
        until(ws)
        conversation = next(iter(app.state.voice_runtime.conversations.values()))

        def seed():
            task = conversation.tasks.create_task("Procedure")
            task.status, task.result = TaskStatus.COMPLETED, "Original result"
            return task

        task = client.portal.call(seed)
        send(ws, "in_first", "Translate the result")
        created = ws.receive_json()
        assert created["type"] == "response.created"
        assert entered.wait(2)
        assert task.status is TaskStatus.COMPLETED
        if interruption == "provider-error":
            failed = until(ws, "error")
            assert not output(failed) and "PRIVATE_PROVIDER" not in repr(failed)
        elif interruption == "response.timeout":
            ws.send_json(
                frame(interruption, response_id=created["response_id"], stage="first_output")
            )
        else:
            ws.send_json(frame(interruption, response_id=created["response_id"], heard_text=""))
        send(ws, "in_retry", "Translate the result again")
        replacement = until(ws)
        assert replacement[0]["in_reply_to"] == ["in_retry"]
        assert output(replacement) == "Translated result."
        assert all(f.get("response_id") != created["response_id"] for f in replacement)
        assert not any(f["type"] == "error" for f in replacement)
        wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
        assert conversation.history[-1].content == "Translated result."
        assert not any(e.content == "Original result" for e in conversation.history)
        if interruption != "provider-error":
            assert cancelled.is_set()
        send(ws, "in_later", "Thanks")
        assert output(until(ws)) == "Welcome."
    assert not agent.workers and not app.state.voice_runtime.conversations
    assert not app.state.voice_runtime._coordinator._detached_tasks
