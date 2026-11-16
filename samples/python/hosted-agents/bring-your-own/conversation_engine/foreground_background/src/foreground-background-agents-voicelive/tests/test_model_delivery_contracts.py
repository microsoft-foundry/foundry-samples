"""Model input/output contracts and delivery's post-send commit boundary."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from azure.ai.agentserver.invocations.voice import ResponseDone
from openai import OpenAI
from starlette.testclient import TestClient
from test_conversation_engine import (
    Chat,
    RecordingSession,
    Responses,
    answer,
    output,
    send,
    start,
    tool,
    until,
    wait_for_server,
)

import worker_agent
from agent_logic import Conversation, ForegroundBackgroundAgent, HistoryEntry, Turn, task_message
from conversation_runtime import HistorySession, create_app
from state import SessionState
from task_store import TaskStatus


@pytest.mark.parametrize(
    "message", ["", " \n\t", None, 7], ids=["empty", "space", "null", "number"]
)
def test_invalid_delivery_claim_cannot_be_committed_by_another_result(message: Any) -> None:
    async def finish_other_task(kwargs: dict) -> Any:
        second.status, second.result, second.finished_at = (
            TaskStatus.COMPLETED,
            "RESULT B ONLY",
            time.time(),
        )
        return tool("respond_directly", message=message, delivered_task_ids=[first.task_id])

    async def retry(kwargs: dict) -> Any:
        return tool("respond_directly", message=first.result, delivered_task_ids=[first.task_id])

    chat = Chat(tool("respond_directly", message="Hello"), finish_other_task, retry)
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_setup", "Hello")
        until(ws)
        conversation = next(iter(app.state.voice_runtime.conversations.values()))

        def seed() -> tuple:
            a = conversation.tasks.create_task("First")
            a.status, a.result = TaskStatus.COMPLETED, "RESULT A NEVER SPOKEN"
            b = conversation.tasks.create_task("Second")
            b.status = TaskStatus.RUNNING
            return a, b

        first, second = client.portal.call(seed)
        send(ws, "in_bad", "Read first")
        frames = []
        while not frames or frames[-1]["type"] not in ("error", "response.done"):
            frames.append(ws.receive_json())
        assert frames[-1]["type"] == "error"
        assert not output(frames)
        assert first.status is second.status is TaskStatus.COMPLETED
        assert all(entry.content != second.result for entry in conversation.history)
        send(ws, "in_retry", "Read first again")
        assert output(until(ws)) == first.result
        wait_for_server(client, lambda: first.status is TaskStatus.DELIVERED)
        assert second.status is TaskStatus.COMPLETED


async def test_empty_unrelated_reply_can_still_deliver_a_newly_completed_result() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Second")
    task.status = TaskStatus.RUNNING

    async def finish(kwargs: dict) -> Any:
        task.status, task.result = TaskStatus.COMPLETED, "RESULT B ONLY"
        return tool("respond_directly", message="", delivered_task_ids=[])

    agent = ForegroundBackgroundAgent(Chat(finish), Responses(), "test")
    turn = Turn("r_empty_ack")
    assert "".join([s async for s in agent.respond(conversation, turn, "Status")]) == task.result
    assert turn.delivered_task_ids == {task.task_id}


@pytest.mark.parametrize("oversized_entry", [False, True], ids=["many-entries", "large-entry"])
async def test_router_and_new_worker_share_bounded_recent_history(oversized_entry: bool) -> None:
    conversation = Conversation()
    # Legal earlier CE replies, collectively much larger than the model-history budget.
    for index in range(18):
        conversation.history.append(HistoryEntry("assistant", str(index) + "x" * 7999))
    if oversized_entry:
        conversation.history.append(HistoryEntry("assistant", "y" * 160_000))
    conversation.history.append(HistoryEntry("user", "Recent question"))
    conversation.history.append(HistoryEntry("assistant", "Unheard answer", "r_heard"))
    conversation.reconcile("r_heard", "HEARD ONLY")
    before = [(e.role, e.content) for e in conversation.history]
    chat = Chat(tool("start_task", request_summary="Find panels", ack_message="Checking."))
    responses = Responses(answer("Panel result"))
    agent = ForegroundBackgroundAgent(chat, responses, "test")
    try:
        assert "Panel result" in "".join(
            [s async for s in agent.respond(conversation, Turn("r_budget"), "Find panels")]
        )
        model_history = chat.requests[0]["messages"][1:-1]
        assert sum(len(m["content"]) for m in model_history) <= 16_000
        worker_history = responses.requests[0]["input"][:-1]
        assert [{"role": m["role"], "content": m["content"]} for m in worker_history] == (
            model_history
        )
        assert model_history[-2:] == [
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "HEARD ONLY"},
        ]
        assert "Unheard answer" not in repr(model_history)
        # Preparing a bounded snapshot must not clip or overwrite retained history.
        assert [(e.role, e.content) for e in conversation.history][:-1] == before[-19:]
    finally:
        await agent.close()


@pytest.mark.parametrize("size", [16_000, 16_001], ids=["exact-budget", "over-budget"])
async def test_model_history_budget_keeps_whole_entries_and_current_input(size: int) -> None:
    conversation = Conversation()
    conversation.history.append(HistoryEntry("assistant", "界" * size))
    chat = Chat(tool("respond_directly", message="Hello"))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    assert "".join([s async for s in agent.respond(conversation, Turn("r_size"), "Now")]) == "Hello"
    messages = chat.requests[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "Now"}
    history = messages[1:-1]
    assert history == ([{"role": "assistant", "content": "界" * size}] if size == 16_000 else [])
    assert conversation.history[0].content == "界" * size


@pytest.mark.parametrize("large", [False, True], ids=["full-context", "explicit-retrieval"])
async def test_recall_after_history_eviction_keeps_full_result_or_requires_lookup(
    large: bool,
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Procedure")
    task.status = TaskStatus.DELIVERED
    task.result = "Initial steps. " + "x" * (7960 if large else 400) + " FINAL STEP"
    conversation.history.append(HistoryEntry("assistant", task.result, "r_original"))
    for index in range(20):
        conversation.history.append(HistoryEntry("user", f"Other turn {index}"))
    assert all(e.response_id != "r_original" for e in conversation.history)

    async def recall(kwargs: dict) -> Any:
        context = "\n".join(m["content"] for m in kwargs["messages"] if m["role"] == "system")
        if large:
            assert "Result bodies omitted" in context and "get_task_result" in context
            assert "Initial steps" not in context
            return tool("get_task_result", task_id=task.task_id)
        assert task.result in context
        return tool(
            "respond_directly", message="Translated FINAL STEP", delivered_task_ids=[task.task_id]
        )

    agent = ForegroundBackgroundAgent(Chat(recall), Responses(), "test")
    turn = Turn("r_recall")
    spoken = "".join([s async for s in agent.respond(conversation, turn, "Repeat or translate")])
    assert spoken == (task.result if large else "Translated FINAL STEP")
    assert task.status is TaskStatus.DELIVERED


@pytest.mark.parametrize("fail", [False, True], ids=["send-returns", "send-fails"])
async def test_delivery_waits_for_server_send_return_not_client_receipt(fail: bool) -> None:
    received, release = asyncio.Event(), asyncio.Event()

    class Transport:
        async def send(self, message: Any) -> None:
            received.set()  # The client can observe the terminal before send returns.
            await release.wait()
            if fail:
                raise RuntimeError("transport failed")

    conversation = Conversation()
    task = conversation.tasks.create_task("Panels")
    task.status, task.result = TaskStatus.COMPLETED, "Result"
    state = SessionState()
    state.try_begin_start()
    state.activate()
    turn = Turn("r_commit", {task.task_id})
    sending = asyncio.create_task(
        HistorySession(Transport(), state, conversation, turn).send(
            ResponseDone(response_id=turn.response_id)
        )
    )
    try:
        await asyncio.wait_for(received.wait(), 1)
        assert task.status is TaskStatus.COMPLETED
    finally:
        release.set()
        result = await asyncio.wait_for(asyncio.gather(sending, return_exceptions=True), 1)
    assert isinstance(result[0], RuntimeError) is fail
    assert task.status is (TaskStatus.COMPLETED if fail else TaskStatus.DELIVERED)
    # Successful retry is idempotent and only commits after its own successful send.
    await HistorySession(RecordingSession(), state, conversation, turn).send(
        ResponseDone(response_id=turn.response_id)
    )
    assert task.status is TaskStatus.DELIVERED


@pytest.mark.parametrize("kind", ["tools", "fifth-answer", "refusal", "empty", "space", "text"])
@pytest.mark.parametrize("cancelled", [False, True], ids=["normal", "cancelled-inflight"])
async def test_real_sdk_worker_final_outcomes_are_truthful(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    cancelled: bool,
) -> None:
    requests, tools = [], []
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    expected_calls = 5 if kind in ("tools", "fifth-answer") else 1
    if cancelled:
        expected_calls = 1

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if cancelled:
            task.cancel_event.set()
        if kind == "tools" or (kind == "fifth-answer" and len(requests) < 5):
            items = [
                {
                    "type": "function_call",
                    "id": f"fc_{len(requests)}",
                    "call_id": f"call_{len(requests)}",
                    "name": "search_site_specs",
                    "arguments": "{}",
                    "status": "completed",
                }
            ]
        else:
            content = (
                [{"type": "refusal", "refusal": "I cannot assist with this request."}]
                if kind == "refusal"
                else [
                    {
                        "type": "output_text",
                        "text": {"empty": "", "space": " \n"}.get(kind, "Panel result"),
                        "annotations": [],
                    }
                ]
            )
            items = [
                {
                    "type": "message",
                    "id": "msg_final",
                    "role": "assistant",
                    "status": "completed",
                    "content": content,
                }
            ]
        return httpx.Response(
            200,
            json={
                "id": f"resp_{len(requests)}",
                "object": "response",
                "created_at": 0,
                "model": "test",
                "status": "completed",
                "output": items,
                "tools": [],
                "tool_choice": "auto",
                "parallel_tool_calls": False,
            },
        )

    def execute(name: str, arguments: dict) -> str:
        tools.append(name)
        return "{}"

    monkeypatch.setattr(worker_agent, "_execute_tool", execute)
    with OpenAI(
        api_key="offline-test",
        base_url="https://offline.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    ) as client:
        await worker_agent.run_worker(task, [], client.responses, "test")
    success = kind in ("text", "fifth-answer") and not (cancelled and kind == "fifth-answer")
    assert task.status is (
        TaskStatus.COMPLETED
        if success
        else TaskStatus.CANCELLED
        if cancelled
        else TaskStatus.FAILED
    )
    assert len(requests) == expected_calls
    assert len(tools) == (
        0 if cancelled else 5 if kind == "tools" else 4 if kind == "fifth-answer" else 0
    )
    assert task.finished_at is not None
    assert "(No response)" not in task.result
    assert "Reached maximum" not in task_message(task)
    agent = ForegroundBackgroundAgent(
        Chat(tool("get_task_result", task_id=task.task_id)), Responses(), "test"
    )
    turn = Turn("r_status")
    spoken = "".join([s async for s in agent.respond(conversation, turn, "Status")])
    assert spoken == task_message(task)
    assert turn.delivered_task_ids == ({task.task_id} if success else set())
    state = SessionState()
    state.try_begin_start()
    state.activate()
    await HistorySession(RecordingSession(), state, conversation, turn).send(
        ResponseDone(response_id=turn.response_id)
    )
    assert task.status is (
        TaskStatus.DELIVERED
        if success
        else TaskStatus.CANCELLED
        if cancelled
        else TaskStatus.FAILED
    )
    # A failed task does not poison later independent work on the same connection.
    retry = conversation.tasks.create_task("Try a new request")
    await worker_agent.run_worker(retry, [], Responses(answer("New result")), "test")
    assert retry.status is TaskStatus.COMPLETED and retry.result == "New result"
