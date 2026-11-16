"""Delivery authority comes from complete results in the actual Router request.

Model doubles may inspect the request, but task-store access is only for arranging
Worker completion, never evidence that the Router saw the newly available answer.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import ResponseDone, ResponseOutputTextDelta
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
    wait_for_server,
)

from agent_logic import Conversation, ForegroundBackgroundAgent, Turn
from conversation_runtime import HistorySession, create_app
from state import SessionState
from task_store import TaskStatus


@pytest.mark.parametrize("status", [TaskStatus.COMPLETED, TaskStatus.DELIVERED])
@pytest.mark.parametrize("over_budget", [False, True], ids=["exact-budget", "index-only"])
async def test_claims_follow_complete_context_not_task_store(
    status: TaskStatus,
    over_budget: bool,
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = status
    prefix = (
        f'Completed task {task.task_id} "{task.query}": '
        if status is TaskStatus.COMPLETED
        else f"DELIVERED: task {task.task_id} — '{task.query}' → "
    )
    # Change one character: the whole 8,000-char context fits, or bodies are omitted.
    task.result = "Full procedure: " + "x" * (8000 + over_budget - len(prefix) - 16)
    claimed_text = "简要翻译。"

    async def route(kwargs: dict) -> Any:
        context = [m["content"] for m in kwargs["messages"][1:] if m["role"] == "system"]
        assert len(context) == 1 and len(context[0]) <= 8000
        assert (task.result in context[0]) is not over_budget
        assert ("Result bodies omitted" in context[0]) is over_budget
        return tool("respond_directly", message=claimed_text, delivered_task_ids=[task.task_id])

    chat = Chat(route, tool("get_task_result", task_id=task.task_id))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_context")
    if over_budget:
        with pytest.raises(ValueError):
            await anext(agent.respond(conversation, turn, "Summarize"))
        assert not turn.delivered_task_ids
        assert all(entry.role == "user" for entry in conversation.history)
    else:
        assert "".join([s async for s in agent.respond(conversation, turn, "Summarize")]) == (
            claimed_text
        )
        assert turn.delivered_task_ids == {task.task_id}
    assert task.status is status
    # An explicit lookup supplies the complete answer even when model context is index-only.
    retry = Turn("r_lookup")
    chunks = [s async for s in agent.respond(conversation, retry, "Read the full result")]
    assert "".join(chunks) == task.result
    assert retry.delivered_task_ids == ({task.task_id} if status is TaskStatus.COMPLETED else set())
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, retry)
    for chunk in chunks:
        await session.send(
            ResponseOutputTextDelta(
                response_id=retry.response_id,
                item_id="out_result",
                delta=chunk,
            )
        )
    assert task.status is status
    with pytest.raises(RuntimeError):
        await HistorySession(RecordingSession(fail=True), state, conversation, retry).send(
            ResponseDone(response_id=retry.response_id)
        )
    assert task.status is status
    await session.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED
    assert conversation.history[-1].content == task.result
    await session.send(ResponseDone(response_id=retry.response_id))
    assert task.status is TaskStatus.DELIVERED  # Replays do not reopen or duplicate delivery.


@pytest.mark.parametrize("route", ["respond_directly", "get_task_result", "check_task_status"])
def test_real_worker_finishing_after_router_snapshot_cannot_be_falsely_delivered(
    route: str,
) -> None:
    entered, release = threading.Event(), threading.Event()
    result = "Use OS2 on panel 1."

    def blocked_model() -> Any:
        entered.set()
        assert release.wait(5)
        return answer(result)

    async def finish_during_routing(kwargs: dict) -> Any:
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        task = conversation.tasks.get("latest")
        assert result not in repr(kwargs["messages"])
        assert task.status is TaskStatus.RUNNING
        release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(agent.workers)), 2)
        assert task.status is TaskStatus.COMPLETED
        if route == "respond_directly":
            return tool(
                route,
                message="Still checking the panel details.",
                delivered_task_ids=[task.task_id],
            )
        return tool(route, task_id=task.task_id, ack_message="Still checking.")

    chat = Chat(
        tool("start_task", request_summary="Find panels", ack_message="Looking."),
        finish_during_routing,
        tool("get_task_result", task_id="latest"),
        tool("respond_directly", message="You're welcome."),
    )
    agent = ForegroundBackgroundAgent(chat, Responses(blocked_model), "test")
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
            send(ws, "in_status", "Status?")
            frames = []
            while not frames or frames[-1]["type"] not in ("error", "response.done"):
                frames.append(ws.receive_json())
            conversation = next(iter(app.state.voice_runtime.conversations.values()))
            task = conversation.tasks.get("latest")
            if route == "respond_directly":
                assert frames[-1]["type"] == "error"
                assert frames[-1]["code"] == "generation_failed"
                assert not output(frames)
                assert not any(f["type"] == "response.done" for f in frames)
                assert sum(f["type"] == "error" for f in frames) == 1
                assert task.status is TaskStatus.COMPLETED
                assert all(e.content != result for e in conversation.history)
            else:
                assert frames[-1]["type"] == "response.done"
                assert output(frames) == result
                wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
            send(ws, "in_retrieve", "Read the result")
            retry = until(ws)
            assert output(retry) == result
            assert retry[0]["in_reply_to"] == ["in_retrieve"]
            wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
            send(ws, "in_later", "Thanks")
            later = until(ws)
            assert output(later) == "You're welcome."
            assert later[0]["in_reply_to"] == ["in_later"]
            assert all(f.get("response_id") != first["response_id"] for f in frames + retry + later)
            assert all(f.get("response_id") != frames[0]["response_id"] for f in retry + later)
            assert not any(f["type"] == "error" for f in retry + later)
            assert len(agent.responses.requests) == 1
        finally:
            release.set()
    assert not agent.workers
    assert not app.state.voice_runtime.conversations


def test_index_only_result_claim_fails_before_speech_then_sdk_lookup_delivers() -> None:
    async def claim_index_only(kwargs: dict) -> Any:
        assert task.result not in repr(kwargs["messages"])
        assert "Result bodies omitted" in repr(kwargs["messages"])
        return tool(
            "respond_directly", message="Still checking.", delivered_task_ids=[task.task_id]
        )

    agent = ForegroundBackgroundAgent(
        Chat(
            tool("respond_directly", message="Hello."),
            claim_index_only,
            tool("get_task_result", task_id="latest"),
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

        def seed() -> Any:
            task = conversation.tasks.create_task("Procedure")
            task.status, task.result = TaskStatus.COMPLETED, "x" * 8000
            return task

        task = client.portal.call(seed)
        send(ws, "in_index", "Read the procedure")
        frames = []
        while not frames or frames[-1]["type"] not in ("error", "response.done"):
            frames.append(ws.receive_json())
        assert frames[-1]["type"] == "error"
        assert frames[-1]["code"] == "generation_failed"
        assert not output(frames)
        assert not any(f["type"] == "response.done" for f in frames)
        assert task.status is TaskStatus.COMPLETED
        assert all(e.content != "Still checking." for e in conversation.history)
        send(ws, "in_lookup", "Read the full result")
        retrieved = until(ws)
        assert retrieved[0]["in_reply_to"] == ["in_lookup"]
        assert output(retrieved) == task.result
        assert all(f.get("response_id") != frames[0]["response_id"] for f in retrieved)
        assert not any(f["type"] == "error" for f in retrieved)
        wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
        send(ws, "in_after_lookup", "Thanks")
        assert output(until(ws)) == "Welcome."
    assert not app.state.voice_runtime.conversations
    assert not agent.workers


async def test_cancelled_router_does_not_authorize_delivery_and_next_turn_can_retry() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status, task.result = TaskStatus.COMPLETED, "Panel result"

    async def held_router(kwargs: dict) -> Any:
        assert task.result in repr(kwargs["messages"])
        entered.set()
        await release.wait()
        return tool("respond_directly", message="Panel summary", delivered_task_ids=[task.task_id])

    agent = ForegroundBackgroundAgent(
        Chat(held_router, tool("get_task_result", task_id=task.task_id)), Responses(), "test"
    )
    turn = Turn("r_cancelled")
    stream = agent.respond(conversation, turn, "Summarize")
    pending = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()
    assert not turn.delivered_task_ids
    assert task.status is TaskStatus.COMPLETED
    assert all(e.role == "user" for e in conversation.history)
    retry = Turn("r_after_cancel")
    assert (
        "".join([s async for s in agent.respond(conversation, retry, "Read result")]) == task.result
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
    assert task.status is TaskStatus.DELIVERED
    assert conversation.history[-1].content == task.result
