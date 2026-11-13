"""Router truthfulness, Worker continuation/cancellation, and bounded history."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    ResponseDone,
    ResponseOutputTextDelta,
)
from openai import OpenAI
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

import worker_agent
from agent_logic import Conversation, ForegroundBackgroundAgent, Turn, task_message
from conversation_runtime import ConversationRuntime, HistorySession, create_app
from router_agent import ROUTER_TOOLS
from state import SessionState
from task_store import TaskStatus


async def test_busy_request_is_declined_and_can_be_retried() -> None:
    conversation = Conversation()
    old = conversation.tasks.create_task("Find panels")
    old.status = TaskStatus.RUNNING
    chat = Chat(
        *[
            tool("start_task", request_summary="Analyze document 12345", ack_message="Analyzing.")
            for _ in range(2)
        ]
    )
    responses = Responses(answer("Document result"))
    agent = ForegroundBackgroundAgent(chat, responses, "test")
    turn = Turn("r_busy")
    stream = agent.respond(conversation, turn, "Analyze document 12345")
    try:
        acknowledgement = await anext(stream)
        assert "Analyzing" not in acknowledgement
        assert "haven't started" in acknowledgement
        assert not agent.workers
        assert conversation.tasks.get("latest") is old
        old.result = "Panel result"
        old.status = TaskStatus.COMPLETED
        assert "Panel result" in "".join([part async for part in stream])
        assert turn.delivered_task_ids == {old.task_id}
        state = SessionState()
        state.try_begin_start()
        state.activate()
        await HistorySession(RecordingSession(), state, conversation, turn).send(
            ResponseDone(response_id=turn.response_id)
        )
        assert old.status is TaskStatus.DELIVERED
        retry = Turn("r_retry")
        result = "".join([part async for part in agent.respond(conversation, retry, "Try again")])
        assert result == "Analyzing.\n\nDocument result"
        new = conversation.tasks.get("latest")
        assert new is not old and new.query == "Analyze document 12345"
        assert retry.delivered_task_ids == {new.task_id}
        assert len(responses.requests) == 1
    finally:
        await stream.aclose()
        await agent.close()


@pytest.mark.parametrize("route", ["check_task_status", "get_task_result"])
@pytest.mark.parametrize("expired", [False, True], ids=["absent", "expired"])
async def test_missing_task_is_not_reported_as_running(route: str, expired: bool) -> None:
    conversation = Conversation()
    if expired:
        task = conversation.tasks.create_task("Old work")
        task.status = TaskStatus.FAILED
        task.finished_at = time.time() - 600
    chat = Chat(
        tool(route, task_id="latest", ack_message="Still working on that."),
        tool("respond_directly", message="Please provide a new request."),
    )
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    text = "".join(
        [part async for part in agent.respond(conversation, Turn("r_missing"), "Status?")]
    )
    assert text.startswith("No task found")
    assert "expired" in text and "evicted" in text
    assert conversation.tasks.get("latest") is None
    assert not agent.workers
    assert (
        "".join([part async for part in agent.respond(conversation, Turn("r_next"), "What next?")])
        == "Please provide a new request."
    )


@pytest.mark.parametrize("status", [TaskStatus.FAILED, TaskStatus.CANCELLED])
@pytest.mark.parametrize("route", ["respond_directly", "check_task_status", "get_task_result"])
@pytest.mark.parametrize("during", ["router", "ack"])
async def test_terminal_worker_outcome_is_reported_once(
    status: TaskStatus,
    route: str,
    during: str,
) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING
    task.result = "PRIVATE_DIAGNOSTIC"

    async def route_request(kwargs: dict) -> Any:
        await asyncio.sleep(0)
        if during == "router":
            task.status = status
        return tool(route, task_id=task.task_id, message="Checking.", ack_message="Checking.")

    agent = ForegroundBackgroundAgent(Chat(route_request), Responses(), "test")
    turn = Turn("r_terminal")
    stream = agent.respond(conversation, turn, "Status?")
    first = await anext(stream)
    if during == "ack":
        assert first == "Checking."
        task.status = status
    result = first + "".join([part async for part in stream])
    terminal = task_message(task)
    assert result.count(terminal) == 1
    assert "PRIVATE" not in result
    assert not turn.delivered_task_ids
    assert task.status is status
    assert not agent.workers


@pytest.mark.parametrize(
    "reported",
    [None, "task-id", [123], ["unknown"], {}],
    ids=["null", "string", "non-string-id", "unknown-id", "object"],
)
async def test_invalid_delivery_ids_fail_before_output_and_allow_retry(reported: Any) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.COMPLETED
    task.result = "Detailed result"
    chat = Chat(
        tool("respond_directly", message="Summary.", delivered_task_ids=reported),
        tool("respond_directly", message="Summary.", delivered_task_ids=[task.task_id]),
    )
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    failed_turn = Turn("r_invalid")
    with pytest.raises(ValueError):
        await anext(agent.respond(conversation, failed_turn, "Summarize"))
    assert not failed_turn.delivered_task_ids
    assert task.status is TaskStatus.COMPLETED
    retry = Turn("r_valid")
    assert (
        "".join([part async for part in agent.respond(conversation, retry, "Try again")])
        == "Summary."
    )
    assert retry.delivered_task_ids == {task.task_id}
    state = SessionState()
    state.try_begin_start()
    state.activate()
    with pytest.raises(RuntimeError):
        await HistorySession(RecordingSession(fail=True), state, conversation, retry).send(
            ResponseDone(response_id=retry.response_id)
        )
    assert task.status is TaskStatus.COMPLETED
    await HistorySession(RecordingSession(), state, conversation, retry).send(
        ResponseDone(response_id=retry.response_id)
    )
    assert task.status is TaskStatus.DELIVERED


def test_missing_delivery_ids_are_a_protocol_error_not_untracked_success() -> None:
    definition = next(item for item in ROUTER_TOOLS if item["name"] == "respond_directly")
    assert "delivered_task_ids" in definition["parameters"]["required"]
    malformed = tool("respond_directly", message="Untracked summary.")
    malformed.choices[0].message.tool_calls[0].function.arguments = json.dumps(
        {"message": "Untracked summary."}
    )
    chat = Chat(malformed, tool("respond_directly", message="Next reply."))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"),
        configure_observability=None,
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_missing_ids", "Summarize")
        frames = until(ws, "error")
        assert not output(frames)
        assert not any(item["type"] == "response.done" for item in frames)
        send(ws, "in_after_error", "Next")
        assert output(until(ws)) == "Next reply."


@pytest.mark.parametrize("kind", ["user.barge_in", "response.cancelled"])
def test_evicted_playback_is_not_appended_as_latest_history(kind: str) -> None:
    chat = Chat(*[tool("respond_directly", message=f"Answer {index}") for index in range(12)])
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"),
        configure_observability=None,
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        for index in range(11):
            send(ws, f"in_{index}", f"Question {index}")
            frames = until(ws)
            if index == 0:
                old_response = frames[0]["response_id"]
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        assert len(conversation.history) == 20
        assert all(entry.response_id != old_response for entry in conversation.history)
        ws.send_json(frame(kind, response_id=old_response, heard_text="OLD HEARD PREFIX"))
        send(ws, "in_after_playback", "Next question")
        assert output(until(ws)) == "Answer 11"
        assert "OLD HEARD PREFIX" not in repr(chat.requests[-1]["messages"])
        assert chat.requests[-1]["messages"][-2] == {"role": "assistant", "content": "Answer 10"}


@pytest.mark.parametrize("callback", ["on_user_barge_in", "on_response_cancelled"])
async def test_first_inflight_send_retains_heard_text(callback: str) -> None:
    entered = asyncio.Event()
    finished = asyncio.Event()
    gate = asyncio.Event()
    sent = []

    class GatedSession(RecordingSession):
        async def send(self, message: Any) -> None:
            if isinstance(message, ResponseOutputTextDelta) and not entered.is_set():
                entered.set()
                await gate.wait()
            sent.append(message)
            if isinstance(message, ResponseDone):
                finished.set()

    chat = Chat(
        tool("respond_directly", message="Already heard. Unheard suffix."),
        tool("respond_directly", message="Next reply."),
    )
    runtime = ConversationRuntime(ForegroundBackgroundAgent(chat, Responses(), "test"))
    session = GatedSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    try:
        await runtime.on_user_message(
            session,
            SimpleNamespace(item_id="in_first", content=[InputTextPart(text="Question")]),
        )
        await asyncio.wait_for(entered.wait(), 1)
        response_id = next(iter(state.responses))
        history_session = state.responses[response_id].session
        assert history_session.first_text_pending
        await getattr(runtime, callback)(
            session,
            SimpleNamespace(response_id=response_id, heard_text="Already heard."),
        )
        conversation = runtime.conversations[session]
        assert conversation.history[-1].content == "Already heard."
        assert conversation.history[-1].response_id == response_id
        await runtime.on_user_message(
            session,
            SimpleNamespace(item_id="in_next", content=[InputTextPart(text="Next")]),
        )
        await asyncio.wait_for(finished.wait(), 1)
        assert not history_session.first_text_pending
        assert {"role": "assistant", "content": "Already heard."} in chat.requests[-1]["messages"]
        assert "Unheard suffix" not in repr(chat.requests[-1]["messages"])
    finally:
        gate.set()
        await runtime.close()


async def test_only_first_delta_can_authorize_missing_history_insertion() -> None:
    flags = []

    class InspectSession(RecordingSession):
        async def send(self, message: Any) -> None:
            flags.append(session.first_text_pending)

    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(InspectSession(), state, Conversation(), Turn("r_flags"))
    for text in ["First part", "Later part"]:
        await session.send(
            ResponseOutputTextDelta(
                response_id="r_flags",
                item_id="out",
                delta=text,
            )
        )
        assert not session.first_text_pending
    assert flags == [True, False]


@pytest.mark.parametrize("cancelled", [False, True], ids=["execute", "cancel-before-entry"])
@pytest.mark.parametrize("stage", ["model", "tool"])
async def test_cancelled_executor_jobs_do_not_start(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    cancelled: bool,
) -> None:
    loop = asyncio.get_running_loop()
    queued = asyncio.Event()
    release = threading.Event()
    task = Conversation().tasks.create_task("Find panels")
    calls = []

    class ObservedPool(ThreadPoolExecutor):
        submissions = 0

        def submit(self, fn, /, *args, **kwargs):
            job = super().submit(fn, *args, **kwargs)
            self.submissions += 1
            if self.submissions == (2 if stage == "model" else 3):
                loop.call_soon_threadsafe(queued.set)
            return job

    pool = ObservedPool(max_workers=1)
    loop.set_default_executor(pool)

    def occupy_thread() -> None:
        assert release.wait(5)

    def execute(name: str, arguments: dict) -> str:
        calls.append(name)
        return "{}"

    def model() -> Any:
        if stage == "tool":
            pool.submit(occupy_thread)
        call = SimpleNamespace(
            type="function_call",
            id="fc_1",
            call_id="call_1",
            name="search_site_specs",
            arguments="{}",
        )
        return answer("", output=[call])

    monkeypatch.setattr(worker_agent, "_execute_tool", execute)
    responses = Responses(model, answer("Panel result"))
    if stage == "model":
        pool.submit(occupy_thread)
    worker = asyncio.create_task(worker_agent.run_worker(task, [], responses, "test"))
    try:
        await asyncio.wait_for(queued.wait(), 2)
        if cancelled:
            task.cancel_event.set()
        release.set()
        await asyncio.wait_for(asyncio.shield(worker), 2)
        if cancelled:
            assert not calls
            assert len(responses.requests) == (0 if stage == "model" else 1)
            assert task.status is TaskStatus.CANCELLED
        else:
            assert calls == ["search_site_specs"]
            assert len(responses.requests) == 2
            assert task.status is TaskStatus.COMPLETED
        assert task.finished_at is not None
    finally:
        release.set()
        await worker
        pool.shutdown(wait=True)


async def test_cancellation_drains_started_tool_without_starting_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    calls = []

    def execute(name: str, arguments: dict) -> str:
        calls.append(name)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        return "{}"

    monkeypatch.setattr(worker_agent, "_execute_tool", execute)
    tool_calls = [
        SimpleNamespace(
            type="function_call",
            id=f"fc_{index}",
            call_id=f"call_{index}",
            name=name,
            arguments="{}",
        )
        for index, name in enumerate(["search_site_specs", "analyze_document"])
    ]
    responses = Responses(answer("", output=tool_calls))
    task = Conversation().tasks.create_task("Find panels")
    worker = asyncio.create_task(worker_agent.run_worker(task, [], responses, "test"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel_event.set()
        await asyncio.sleep(0)
        assert not worker.done()
        release.set()
        await asyncio.wait_for(asyncio.shield(worker), 2)
        assert calls == ["search_site_specs"]
        assert len(responses.requests) == 1
        assert task.status is TaskStatus.CANCELLED
        assert task.finished_at is not None
    finally:
        release.set()
        await worker


@pytest.mark.parametrize("reasoning", [False, True], ids=["plain", "reasoning"])
@pytest.mark.parametrize("tool_failure", [False, True], ids=["tool-success", "tool-failure"])
async def test_worker_replays_all_output_items_in_order(
    monkeypatch: pytest.MonkeyPatch,
    reasoning: bool,
    tool_failure: bool,
) -> None:
    requests = []
    returned = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        index = len(requests)
        items = []
        if index < 3:
            if reasoning:
                items.append(
                    {
                        "id": f"rs_{index}",
                        "type": "reasoning",
                        "summary": [],
                        "encrypted_content": f"opaque_{index}",
                    }
                )
            items.append(
                {
                    "id": f"msg_{index}",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": "Checking sources.", "annotations": []}
                    ],
                }
            )
            for suffix in ["a", "b"] if index == 1 else ["c"]:
                items.append(
                    {
                        "id": f"fc_{suffix}",
                        "type": "function_call",
                        "call_id": f"call_{suffix}",
                        "name": "search_site_specs",
                        "arguments": "{}",
                        "status": "completed",
                    }
                )
        else:
            items.append(
                {
                    "id": "msg_final",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "Panel result", "annotations": []}],
                }
            )
        returned.append(items)
        return httpx.Response(
            200,
            json={
                "id": f"resp_{index}",
                "object": "response",
                "created_at": 0,
                "model": "test",
                "status": "completed",
                "output": items,
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    def execute(name: str, arguments: dict) -> str:
        if tool_failure:
            raise RuntimeError("PRIVATE_TOOL_DIAGNOSTIC")
        return "{}"

    monkeypatch.setattr(worker_agent, "_execute_tool", execute)
    task = Conversation().tasks.create_task("Find panels")
    with OpenAI(
        api_key="offline-test",
        base_url="https://offline.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    ) as client:
        await worker_agent.run_worker(
            task,
            [{"type": "message", "role": "user", "content": "Find panels"}],
            client.responses,
            "test",
        )
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "Panel result"
    assert len(requests) == 3
    for index in range(2):
        expected_prefix = requests[index]["input"] + returned[index]
        replay = requests[index + 1]["input"]
        assert replay[: len(expected_prefix)] == expected_prefix
        results = replay[len(expected_prefix) :]
        assert [item["call_id"] for item in results] == [
            item["call_id"] for item in returned[index] if item["type"] == "function_call"
        ]
        assert all(item["type"] == "function_call_output" for item in results)
        assert "PRIVATE_TOOL_DIAGNOSTIC" not in repr(results)
    assert all(request["store"] is False for request in requests)
    assert all(request["include"] == ["reasoning.encrypted_content"] for request in requests)
