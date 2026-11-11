"""Model-free tests through the real SDK CE dispatcher and original Worker loop."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import (
    ResponseDone,
    ResponseOutputTextDelta,
)
from starlette.testclient import TestClient

from agent_logic import Conversation, ForegroundBackgroundAgent, Turn, text_chunks
from conversation_runtime import ConversationRuntime, HistorySession, create_app
from scripts.smoke_test import run as run_smoke
from state import MAX_TERMINAL_SENDS, SessionState
from task_store import TaskStatus


def tool(name: str, **arguments: Any) -> Any:
    if name == "respond_directly":
        arguments.setdefault("delivered_task_ids", [])
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name=name,
                                arguments=json.dumps(arguments),
                            )
                        )
                    ],
                )
            )
        ]
    )


class Chat:
    def __init__(self, *steps: Any) -> None:
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return await step(kwargs)
        return step


class Responses:
    def __init__(self, *steps: Any) -> None:
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        step = self.steps.pop(0)
        return step() if callable(step) else step


def answer(text: str, status: str = "completed", output: list | None = None) -> Any:
    return SimpleNamespace(status=status, output_text=text, output=output or [])


def frame(kind: str, **fields: Any) -> dict:
    return {"type": kind, "id": f"m_{uuid.uuid4().hex}", "ts": "2026-11-10T00:00:00Z", **fields}


def start(ws: Any, protocol: str = "1.0") -> dict:
    ws.send_json(
        frame(
            "session.start",
            protocol_version=protocol,
            reconnect=False,
            response_timeouts={
                "first_output_ms": 30000,
                "idle_ms": 30000,
                "max_duration_ms": 120000,
            },
        )
    )
    return ws.receive_json()


def send(ws: Any, item_id: str, text: str) -> None:
    ws.send_json(
        frame("user.message", item_id=item_id, content=[{"type": "input_text", "text": text}])
    )


def until(ws: Any, terminal: str = "response.done") -> list[dict]:
    frames = []
    while True:
        frame = ws.receive_json()
        frames.append(frame)
        if frame["type"] == terminal:
            return frames


def output(frames: list[dict]) -> str:
    return "".join(
        frame["delta"] for frame in frames if frame["type"] == "response.output_text.delta"
    )


def wait_for_server(client: TestClient, predicate: Callable[[], bool]) -> None:
    # Client receipt can precede the server's post-send bookkeeping continuation.
    async def wait() -> None:
        async with asyncio.timeout(2):
            for _ in range(200):
                if predicate():
                    return
                await asyncio.sleep(0.01)
            assert predicate(), "Server bookkeeping did not settle"

    client.portal.call(wait)


@pytest.mark.parametrize("route", ["/voice_conversation_engine", "/invocations_ws"])
def test_direct_router_response_and_history(route: str) -> None:
    chat = Chat(
        tool("respond_directly", message="Hello."), tool("respond_directly", message="Second.")
    )
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect(route) as ws:
        assert start(ws)["type"] == "session.ready"
        send(ws, "in_1", "First")
        first = until(ws)
        assert output(first) == "Hello."
        assert first[0]["in_reply_to"] == ["in_1"]
        send(ws, "in_2", "Second")
        until(ws)
        assert client.post("/responses", json={}).status_code == 404
    messages = chat.requests[1]["messages"]
    assert {"role": "assistant", "content": "Hello."} in messages
    assert chat.requests[0]["parallel_tool_calls"] is False
    assert app.state.voice_runtime.conversations == {}


def test_handshake_rejects_other_message_protocol() -> None:
    chat = Chat()
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws, "2.0")["type"] == "session.rejected"
    assert not chat.requests


def test_connections_do_not_share_history_or_tasks() -> None:
    chat = Chat(
        tool("respond_directly", message="First private answer"),
        tool("respond_directly", message="Second private answer"),
    )
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client:
        with client.websocket_connect("/voice_conversation_engine") as first:
            start(first)
            send(first, "in_same", "First private question")
            until(first)
            with client.websocket_connect("/voice_conversation_engine") as second:
                start(second)
                send(second, "in_same", "Second private question")
                until(second)
                assert len(app.state.voice_runtime.conversations) == 2
    assert "First private" not in repr(chat.requests[1])


def test_real_worker_executes_domain_tool_and_delivers(monkeypatch: pytest.MonkeyPatch) -> None:
    import worker_agent

    seen = []

    def execute(name: str, arguments: dict) -> str:
        seen.append((name, arguments))
        return '{"panel": "OS2"}'

    monkeypatch.setattr(worker_agent, "_execute_tool", execute)
    call = SimpleNamespace(
        type="function_call",
        id="fc_1",
        call_id="call_1",
        name="search_site_specs",
        arguments='{"site_name":"Quincy"}',
    )
    responses = Responses(answer("", output=[call]), answer("Use OS2 on panel 1."))
    chat = Chat(tool("start_task", request_summary="Find Quincy panels", ack_message="On it."))
    app = create_app(
        ForegroundBackgroundAgent(chat, responses, "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_task", "Find Quincy panels")
        frames = until(ws)
        assert output(frames) == "On it.\n\nUse OS2 on panel 1."
        conversation = next(iter(app.state.voice_runtime.conversations.values()))
        wait_for_server(
            client, lambda: conversation.tasks.get("latest").status is TaskStatus.DELIVERED
        )
    assert seen == [("search_site_specs", {"site_name": "Quincy"})]
    assert len(responses.requests) == 2


def test_barge_in_reconciles_sent_history() -> None:
    chat = Chat(
        tool("respond_directly", message="Heard prefix. Unheard suffix."),
        tool("respond_directly", message="New answer"),
    )
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_1", "Question")
        first = until(ws)
        ws.send_json(
            frame("user.barge_in", response_id=first[0]["response_id"], heard_text="Heard prefix.")
        )
        send(ws, "in_2", "Next question")
        until(ws)
    assert {"role": "assistant", "content": "Heard prefix."} in chat.requests[1]["messages"]
    assert "Unheard suffix" not in repr(chat.requests[1])


def test_timeout_interrupts_router_and_receive_loop_accepts_next_turn() -> None:
    started = threading.Event()
    cancelled = threading.Event()

    async def blocked(kwargs: dict) -> Any:
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    chat = Chat(blocked, tool("respond_directly", message="Replacement"))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_a", "Blocked question")
        created = ws.receive_json()
        assert started.wait(2)
        ws.send_json(
            frame("response.timeout", response_id=created["response_id"], stage="first_output")
        )
        send(ws, "in_b", "Replacement question")
        assert output(until(ws)) == "Replacement"
        assert cancelled.is_set()
    assert not any(message["role"] == "assistant" for message in chat.requests[1]["messages"][:-1])


def test_router_errors_are_protocol_errors_not_spoken_diagnostics() -> None:
    chat = Chat(RuntimeError("PRIVATE_PROVIDER_DETAIL"))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_failure", "Question")
        frames = until(ws, "error")
    assert not output(frames)
    assert "PRIVATE_PROVIDER_DETAIL" not in repr(frames)


class RecordingSession:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def send(self, message: Any) -> None:
        if self.fail:
            raise RuntimeError("backpressure or disconnected transport")


async def test_delivery_uses_explicit_task_ids_not_matching_text() -> None:
    conversation = Conversation()
    first, second = [conversation.tasks.create_task(str(i)) for i in range(2)]
    first.status = second.status = TaskStatus.COMPLETED
    first.result, second.result = "1", "10"
    turn = Turn("r_test", {second.task_id})
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, turn)
    await session.send(
        ResponseOutputTextDelta(
            response_id=turn.response_id,
            item_id="out",
            delta="The second answer is ten.",
        )
    )
    assert first.status is second.status is TaskStatus.COMPLETED
    await session.send(ResponseDone(response_id=turn.response_id))
    assert second.status is TaskStatus.DELIVERED
    assert first.status is TaskStatus.COMPLETED


async def test_failed_send_does_not_commit_history_or_delivery() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Query")
    task.status = TaskStatus.COMPLETED
    turn = Turn("r_test", {task.task_id})
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(fail=True), state, conversation, turn)
    with pytest.raises(RuntimeError):
        await session.send(
            ResponseOutputTextDelta(
                response_id=turn.response_id,
                item_id="out",
                delta="NEVER SENT",
            )
        )
    with pytest.raises(RuntimeError):
        await session.send(ResponseDone(response_id=turn.response_id))
    assert not conversation.history
    assert not session.first_text_pending
    assert task.status is TaskStatus.COMPLETED


@pytest.mark.parametrize("status", ["failed", "incomplete"])
async def test_worker_unsuccessful_outcomes_are_not_delivered(status: str) -> None:
    from worker_agent import run_worker

    task = Conversation().tasks.create_task("Query")
    await run_worker(task, [], Responses(answer("PRIVATE_PARTIAL", status)), "test")
    assert task.status is TaskStatus.FAILED
    assert "PRIVATE" not in task.result


async def test_cancellation_settling_during_ack_is_reported() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Query")
    task.status = TaskStatus.RUNNING
    chat = Chat(tool("check_task_status", task_id=task.task_id, ack_message="Still working."))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    stream = agent.respond(conversation, Turn("r_status"), "Status?")
    assert await anext(stream) == "Still working."
    task.status = TaskStatus.CANCELLED
    rest = "".join([chunk async for chunk in stream])
    assert "cancelled" in rest


async def test_shutdown_remains_owned_when_joining_callback_is_cancelled() -> None:
    gate = asyncio.Event()
    agent = ForegroundBackgroundAgent(Chat(), Responses(), "test")
    worker = asyncio.create_task(gate.wait())
    agent.workers.add(worker)
    worker.add_done_callback(agent.workers.discard)
    runtime = ConversationRuntime(agent)
    first_join = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    first_join.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_join
    second_join = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    assert not second_join.done()
    assert not worker.cancelled()
    gate.set()
    await asyncio.wait_for(second_join, 2)


def test_worker_survives_barge_in_and_result_is_delivered_next_turn() -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked() -> Any:
        started.set()
        assert release.wait(5)
        return answer("Worker result")

    responses = Responses(blocked)
    chat = Chat(
        tool("start_task", request_summary="Find panels", ack_message="Looking."),
        tool("respond_directly", message="Checking."),
    )
    app = create_app(
        ForegroundBackgroundAgent(chat, responses, "test"), configure_observability=None
    )
    try:
        with (
            TestClient(app) as client,
            client.websocket_connect("/voice_conversation_engine") as ws,
        ):
            start(ws)
            send(ws, "in_a", "Find panels")
            created = ws.receive_json()
            assert ws.receive_json()["type"] == "response.output_text.delta"
            assert started.wait(2)
            ws.send_json(
                frame("user.barge_in", response_id=created["response_id"], heard_text="Look")
            )
            send(ws, "in_b", "How is it going?")
            replacement = ws.receive_json()
            assert replacement["type"] == "response.created"
            assert replacement["response_id"] != created["response_id"]
            assert ws.receive_json()["type"] == "response.output_text.delta"
            conversation = next(iter(app.state.voice_runtime.conversations.values()))
            assert not conversation.tasks.get("latest").cancel_event.is_set()
            release.set()
            frames = until(ws)
            assert output(frames) == "\n\nWorker result"
            assert all(item.get("response_id") != created["response_id"] for item in frames)
    finally:
        release.set()
    assert len(responses.requests) == 1


async def test_no_input_signals_worker_before_backpressured_terminal_send() -> None:
    from azure.ai.agentserver.invocations.voice import EndCall

    gate = asyncio.Event()
    end_call_started = asyncio.Event()

    class BackpressuredSession(RecordingSession):
        async def send(self, message: Any) -> None:
            if isinstance(message, EndCall):
                end_call_started.set()
                await gate.wait()

    agent = ForegroundBackgroundAgent(Chat(), Responses(), "test")
    runtime = ConversationRuntime(agent)
    session = BackpressuredSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    conversation = Conversation()
    runtime.conversations[session] = conversation
    task = conversation.tasks.create_task("Query")
    task.status = TaskStatus.RUNNING
    await asyncio.wait_for(
        runtime.on_user_no_input(
            session,
            SimpleNamespace(item_id="in_idle", count=3),
        ),
        1,
    )
    assert task.cancel_event.is_set()
    await asyncio.wait_for(end_call_started.wait(), 1)
    assert not gate.is_set()
    gate.set()
    await runtime.close()


async def test_duplicate_no_input_does_not_cancel_business_work() -> None:
    agent = ForegroundBackgroundAgent(Chat(), Responses(), "test")
    runtime = ConversationRuntime(agent)
    session = RecordingSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    state.claim_input("in_repeat")
    conversation = Conversation()
    runtime.conversations[session] = conversation
    task = conversation.tasks.create_task("Query")
    task.status = TaskStatus.RUNNING
    await runtime.on_user_no_input(session, SimpleNamespace(item_id="in_repeat", count=3))
    assert not task.cancel_event.is_set()
    assert state.active
    await runtime.close()


async def test_terminal_capacity_cancels_worker_before_backpressured_end_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure.ai.agentserver.invocations.voice import EndCall, InputTextPart, UserMessage

    import worker_agent

    entered = threading.Event()
    release = threading.Event()
    transport_gate = asyncio.Event()
    end_call_started = asyncio.Event()
    end_calls = []
    tools = []

    def blocked_model() -> Any:
        entered.set()
        assert release.wait(5)
        call = SimpleNamespace(type="function_call", name="search_site_specs")
        return answer("", output=[call])

    class BackpressuredSession(RecordingSession):
        async def send(self, message: Any) -> None:
            if isinstance(message, EndCall):
                end_calls.append(message)
                end_call_started.set()
            await transport_gate.wait()

    monkeypatch.setattr(worker_agent, "_execute_tool", lambda *args: tools.append(args))
    responses = Responses(blocked_model)
    agent = ForegroundBackgroundAgent(Chat(), responses, "test")
    runtime = ConversationRuntime(agent)
    session = BackpressuredSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    conversation = Conversation()
    runtime.conversations[session] = conversation
    task = conversation.tasks.create_task("Find panels")
    agent.start_worker(task, [])
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        for index in range(MAX_TERMINAL_SENDS):
            await runtime.on_user_message(
                session,
                UserMessage(
                    id=f"m_{index}",
                    ts="2026-11-10T00:00:00Z",
                    item_id=f"in_{index}",
                    content=(InputTextPart(text=" "),),
                ),
            )
        assert state.active
        assert state.terminal_send_count == MAX_TERMINAL_SENDS
        assert runtime.conversations[session] is conversation
        assert not task.cancel_event.is_set()

        await asyncio.wait_for(
            runtime.on_user_message(
                session,
                UserMessage(
                    id="m_overflow",
                    ts="2026-11-10T00:00:00Z",
                    item_id="in_overflow",
                    content=(InputTextPart(text=" "),),
                ),
            ),
            1,
        )
        assert not state.active
        assert session not in runtime.conversations
        assert task.cancel_event.is_set()
        await asyncio.wait_for(end_call_started.wait(), 1)
        assert not transport_gate.is_set()

        release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(agent.workers)), 2)
        assert task.status is TaskStatus.CANCELLED
        assert not tools
        assert len(responses.requests) == 1
        await runtime.on_user_message(
            session,
            UserMessage(
                id="m_late",
                ts="2026-11-10T00:00:00Z",
                item_id="in_late",
                content=(InputTextPart(text="More work"),),
            ),
        )
        assert not agent.chat.requests
        assert len(end_calls) == 1
    finally:
        release.set()
        transport_gate.set()
        await asyncio.wait_for(runtime.close(), 2)
    assert not agent.workers
    assert not runtime._coordinator._detached_tasks


def test_real_worker_finishing_during_router_is_delivered_in_same_turn() -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocked_model() -> Any:
        entered.set()
        assert release.wait(5)
        return answer("Use OS2 on panel 1.")

    async def finish_during_routing(kwargs: dict) -> Any:
        assert "RUNNING:" in repr(kwargs["messages"])
        assert agent.workers
        release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(agent.workers)), 2)
        return tool("respond_directly", message="Checking.")

    chat = Chat(
        tool("start_task", request_summary="Find panels", ack_message="Looking."),
        finish_during_routing,
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
            frames = until(ws)
            expected = "Checking.\n\nUse OS2 on panel 1."
            assert output(frames) == expected
            assert frames[0]["in_reply_to"] == ["in_status"]
            assert all(item.get("response_id") != first["response_id"] for item in frames)
            assert sum(item["type"] == "response.done" for item in frames) == 1
            conversation = next(iter(app.state.voice_runtime.conversations.values()))
            wait_for_server(
                client, lambda: conversation.tasks.get("latest").status is TaskStatus.DELIVERED
            )
            send(ws, "in_thanks", "Thanks")
            assert output(until(ws)) == "You're welcome."
            assert {"role": "assistant", "content": expected} in chat.requests[2]["messages"]
        finally:
            release.set()
    assert not agent.workers


@pytest.mark.parametrize("route", ["respond_directly", "check_task_status", "get_task_result"])
async def test_result_completed_during_router_is_delivered_once(route: str) -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING

    async def finish_during_routing(kwargs: dict) -> Any:
        assert "RUNNING:" in repr(kwargs["messages"])
        await asyncio.sleep(0)
        task.result = "Use OS2 on panel 1."
        task.status = TaskStatus.COMPLETED
        if route == "respond_directly":
            return tool(route, message="Checking.")
        return tool(route, task_id=task.task_id, ack_message="Checking.")

    chat = Chat(finish_during_routing, tool("respond_directly", message="You're welcome."))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_finished_during_router")
    chunks = [chunk async for chunk in agent.respond(conversation, turn, "Status?")]
    expected = (
        "Checking.\n\nUse OS2 on panel 1."
        if route == "respond_directly"
        else "Use OS2 on panel 1."
    )
    assert "".join(chunks) == expected
    assert turn.delivered_task_ids == {task.task_id}
    assert task.status is TaskStatus.COMPLETED

    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = HistorySession(RecordingSession(), state, conversation, turn)
    for chunk in chunks:
        await session.send(
            ResponseOutputTextDelta(response_id=turn.response_id, item_id="out", delta=chunk)
        )
    assert conversation.history[-1].content == expected
    await session.send(ResponseDone(response_id=turn.response_id))
    assert task.status is TaskStatus.DELIVERED
    next_turn = Turn("r_after_delivery")
    assert "".join(
        [chunk async for chunk in agent.respond(conversation, next_turn, "Thanks")]
    ) == "You're welcome."
    assert not next_turn.delivered_task_ids


@pytest.mark.parametrize(
    "ack",
    ["", "Checking panel specifications and the latest site records."],
    ids=["empty-ack", "chunked-ack"],
)
async def test_separators_only_between_nonempty_utterances(
    monkeypatch: pytest.MonkeyPatch,
    ack: str,
) -> None:
    import agent_logic

    monkeypatch.setattr(agent_logic, "STATUS_INTERVAL", 0)
    conversation = Conversation()
    task = conversation.tasks.create_task("Find panels")
    task.status = TaskStatus.RUNNING
    status = "Checking the current fiber specifications and recent site updates."
    result = "Use OS2 on panel 1, and verify the current fiber map before proceeding."

    async def finish(kwargs: dict) -> Any:
        task.result = result
        task.status = TaskStatus.COMPLETED
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Stale"))])

    chat = Chat(
        tool("respond_directly", message=ack),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=status))]),
        finish,
    )
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    chunks = [chunk async for chunk in agent.respond(conversation, Turn("r_segments"), "Status?")]
    utterances = [text for text in (ack, status, result) if text]
    expected_chunks = []
    for text in utterances:
        if expected_chunks:
            expected_chunks.append("\n\n")
        expected_chunks.extend(text_chunks(text))
    assert chunks == expected_chunks
    assert "".join(chunks) == "\n\n".join(utterances)


async def test_router_paraphrase_tracks_completed_task_by_id() -> None:
    conversation = Conversation()
    task = conversation.tasks.create_task("Specifications")
    task.status = TaskStatus.COMPLETED
    task.result = "Very long original English specification."
    chat = Chat(tool("respond_directly", message="简短总结。", delivered_task_ids=[task.task_id]))
    agent = ForegroundBackgroundAgent(chat, Responses(), "test")
    turn = Turn("r_paraphrase")
    assert (
        "".join([text async for text in agent.respond(conversation, turn, "Summarize")])
        == "简短总结。"
    )
    assert turn.delivered_task_ids == {task.task_id}
    assert task.status is TaskStatus.COMPLETED


def test_fresh_terminal_outcome_is_not_expired_by_old_creation_time() -> None:
    import time

    conversation = Conversation()
    task = conversation.tasks.create_task("Long-running work")
    task.created_at = time.time() - 600
    task.status = TaskStatus.FAILED
    task.finished_at = time.time()
    conversation.tasks.cleanup()
    assert conversation.tasks.get("latest") is task


def test_expired_latest_task_does_not_select_an_older_result() -> None:
    import time

    conversation = Conversation()
    older = conversation.tasks.create_task("Older result")
    older.status = TaskStatus.COMPLETED
    latest = conversation.tasks.create_task("Latest work")
    latest.status = TaskStatus.FAILED
    latest.finished_at = time.time() - 600
    conversation.tasks.cleanup()
    assert conversation.tasks.get("latest") is None


def test_missing_history_is_not_appended_without_a_pending_first_send() -> None:
    conversation = Conversation()
    conversation.reconcile("r_pending_send", "Already heard")
    assert not conversation.history


async def test_real_model_client_factories_can_close_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/test"
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test")
    agent = ForegroundBackgroundAgent.from_environment()
    await agent.close()


async def test_dedicated_smoke_client_uses_real_ce_websocket() -> None:
    import websockets
    from hypercorn.config import Config
    from hypercorn.utils import wrap_app

    chat = Chat(tool("respond_directly", message="你好，field operations ready."))
    app = create_app(
        ForegroundBackgroundAgent(chat, Responses(), "test"), configure_observability=None
    )
    config = Config()
    config.bind = ["127.0.0.1:0"]
    config.accesslog = None
    sockets = config.create_sockets()
    port = sockets.insecure_sockets[0].getsockname()[1]
    shutdown = asyncio.Event()
    # Use Hypercorn's normal worker server on an OS-assigned port; no cloud fixture.
    from hypercorn.asyncio.run import worker_serve

    server = asyncio.create_task(
        worker_serve(
            wrap_app(app, config.wsgi_max_body_size, None),
            config,
            sockets=sockets,
            shutdown_trigger=shutdown.wait,
        )
    )
    try:
        for _ in range(100):
            try:
                async with websockets.connect(f"ws://127.0.0.1:{port}/voice_conversation_engine"):
                    break
            except OSError:
                await asyncio.sleep(0.01)
        await run_smoke(f"ws://127.0.0.1:{port}/voice_conversation_engine", "Hello")
    finally:
        shutdown.set()
        await asyncio.wait_for(server, 5)
