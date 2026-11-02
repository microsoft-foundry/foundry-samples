# Copyright (c) Microsoft. All rights reserved.

"""Real CE socket tests with only the original handler's model/worker calls replaced."""

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import InputTextPart
from starlette.testclient import TestClient

from main import create_app
from task_store import TaskStatus


def frame(kind, **fields):
    return {"type": kind, "id": f"m_{uuid.uuid4().hex}", "ts": "2026-11-02T00:00:00Z", **fields}


def start(ws, version="1.0"):
    ws.send_json(
        frame(
            "session.start",
            protocol_version=version,
            reconnect=False,
            response_timeouts={
                "first_output_ms": 30_000,
                "idle_ms": 30_000,
                "max_duration_ms": 120_000,
            },
        )
    )
    return ws.receive_json()


def send_user(ws, text, item_id="in_1"):
    ws.send_json(
        frame("user.message", item_id=item_id, content=[{"type": "input_text", "text": text}])
    )


def receive_until(ws, kind):
    events = []
    while not events or events[-1]["type"] != kind:
        event = ws.receive_json()
        assert event["type"] != "error", event
        events.append(event)
    return events


def output(events):
    return "".join(e.get("delta", "") for e in events)


@pytest.fixture
def logic(monkeypatch):
    # These are inert local test values, never deployment configuration.
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/test")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-model")
    import agent_logic

    async def router(_client, _model, _instructions, items, tools, tool_choice=None):
        text = items[-1]["content"]
        if tools is None:
            yield SimpleNamespace(type="response.output_text.delta", delta="Still working.")
            return
        if text.startswith("search"):
            name, args = "start_task", {"request_summary": text, "ack_message": "Looking that up."}
        elif text == "cancel":
            name, args = "cancel_task", {"task_id": "latest", "ack_message": "Cancelled."}
        elif text == "status":
            name, args = "check_task_status", {"task_id": "latest", "ack_message": "Checking."}
        else:
            name, args = "respond_directly", {"message": text}
        yield SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args)),
        )

    monkeypatch.setattr(agent_logic, "_iter_llm_stream", router)
    return agent_logic


class Worker:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.calls = 0

    async def __call__(self, task, _input, _client, _model):
        self.calls += 1
        task.status = TaskStatus.RUNNING
        self.started.set()
        try:
            while not self.release.is_set():
                if task.cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    self.cancelled.set()
                    return
                await asyncio.sleep(0.005)
            task.result = f"Result for {task.query}: OS2, Row C, Rack 7."
            task.status = TaskStatus.COMPLETED
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.parametrize("text", ["hello", "  你好 👋\n", "/end", "x" * 8000])
def test_original_router_text_streams_over_ce(logic, text):
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, text)
        events = receive_until(ws, "response.done")
        assert events[0]["in_reply_to"] == ["in_1"]
        assert output(events) == text
        assert events[-2]["text"] == text
        assert all(e["response_id"] == events[0]["response_id"] for e in events)


def assert_private_logs(caplog, marker):
    records = [
        record for record in caplog.records
        if record.name in {"agent_logic", "worker_agent", "voice_live_bridge"}
    ]
    assert records
    for record in records:
        assert marker not in record.getMessage()
        assert marker not in repr(record.args)
        assert record.exc_info is None
        assert not record.stack_info
    return records


def test_original_handler_does_not_log_customer_input_or_tool_arguments(logic, caplog):
    import logging

    marker = "SYNTHETIC_CUSTOMER_PROMPT_AND_CREDENTIAL_DO_NOT_LOG"
    caplog.set_level(logging.INFO)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, marker)
        assert output(receive_until(ws, "response.done")) == marker
    assert_private_logs(caplog, marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["router", "status"])
async def test_original_handler_exception_logs_are_private(
    logic, monkeypatch, caplog, failure_point
):
    import logging

    from voice_runtime import Conversation, ResponseContextAdapter

    marker = "SYNTHETIC_UPSTREAM_EXCEPTION_DO_NOT_LOG"
    caplog.set_level(logging.INFO)
    conversation = Conversation()
    context = ResponseContextAdapter("r_private", marker, [], conversation)
    signal = asyncio.Event()
    if failure_point == "status":
        conversation.task_store.create_task(marker).status = TaskStatus.RUNNING
        # A handler-local clock triggers a periodic status call without waiting five seconds.
        times = iter([0.0, 6.0])
        local_asyncio = SimpleNamespace(**vars(asyncio))
        local_asyncio.get_event_loop = lambda: SimpleNamespace(time=lambda: next(times))
        monkeypatch.setattr(logic, "asyncio", local_asyncio)
        monkeypatch.setattr(logic, "_TASK_POLL_INTERVAL", 0)

    async def router(_client, _model, _instructions, _items, tools, **_kwargs):
        if failure_point == "router" or tools is None:
            signal.set()
            raise RuntimeError(marker) from ValueError("nested_" + marker)
        yield SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(
                type="function_call", name="respond_directly", arguments={"message": "ack"}
            ),
        )

    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    events = [event async for event in logic.handler({"stream": True}, context, signal)]
    assert events[-1]["type"] == "response.completed"
    records = assert_private_logs(caplog, marker)
    assert any("RuntimeError" in record.getMessage() for record in records)
    assert context.response_id not in logic._active_cancel_signals


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["model", "tool"])
async def test_original_worker_exception_logs_are_private(monkeypatch, caplog, failure_point):
    import logging

    import worker_agent
    from task_store import Task

    marker = "SYNTHETIC_UPSTREAM_EXCEPTION_DO_NOT_LOG"
    caplog.set_level(logging.INFO)
    calls = 0

    def fail_tool(*_args):
        raise RuntimeError(marker) from ValueError("nested_" + marker)

    def model(**_kwargs):
        nonlocal calls
        calls += 1
        if failure_point == "model":
            fail_tool()
        if calls == 1:
            return SimpleNamespace(
                output=[SimpleNamespace(
                    type="function_call", name="search_site_specs", arguments={"query": marker},
                    id="call_1", call_id="call_1",
                )],
                output_text="",
            )
        return SimpleNamespace(output=[], output_text="finished")

    monkeypatch.setattr(worker_agent, "_execute_tool", fail_tool)
    task = Task(task_id="task_private", query=marker)
    await worker_agent.run_worker(task, [], SimpleNamespace(create=model), "test-model")
    assert task.status is (TaskStatus.FAILED if failure_point == "model" else TaskStatus.COMPLETED)
    records = assert_private_logs(caplog, marker)
    assert any("RuntimeError" in record.getMessage() for record in records)


@pytest.mark.parametrize("text", ["", "x" * 8001])
def test_invalid_input_is_resolved_without_model(logic, text):
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, text)
        assert ws.receive_json()["type"] == "response.none"


@pytest.mark.parametrize("control", ["user.barge_in", "response.cancelled", "response.timeout"])
def test_interrupt_keeps_worker_and_next_turn_gets_result(logic, monkeypatch, control):
    worker = Worker()
    monkeypatch.setattr(logic, "run_worker", worker)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, "search Quincy North")
        ack = receive_until(ws, "response.output_text.delta")
        assert output(ack) == "Looking that up."
        assert worker.started.wait(2)
        response_id = ack[0]["response_id"]
        fields = {"response_id": response_id}
        if control != "response.timeout":
            fields["heard_text"] = "Looking"
        else:
            fields["stage"] = "max_duration"
        ws.send_json(frame(control, **fields))
        send_user(ws, "hello again", "in_2")
        reply = receive_until(ws, "response.output_text.delta")
        assert output(reply) == "hello again"
        assert not worker.cancelled.is_set()
        assert worker.calls == 1
        worker.release.set()
        result = receive_until(ws, "response.done")
        assert "OS2, Row C, Rack 7" in output(result)


def test_ack_then_wait_then_result_in_one_response(logic, monkeypatch):
    worker = Worker()
    monkeypatch.setattr(logic, "run_worker", worker)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, "search Quincy North")
        ack = receive_until(ws, "response.output_text.delta")
        assert output(ack) == "Looking that up."
        assert worker.started.wait(2)
        worker.release.set()
        result = receive_until(ws, "response.done")
        assert output(ack + result) == (
            "Looking that up.\n\nResult for search Quincy North: OS2, Row C, Rack 7."
        )
        assert all(e["response_id"] == ack[0]["response_id"] for e in result)


def test_explicit_cancel_stops_worker(logic, monkeypatch):
    worker = Worker()
    monkeypatch.setattr(logic, "run_worker", worker)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, "search Quincy North")
        ack = receive_until(ws, "response.output_text.delta")
        assert worker.started.wait(2)
        ws.send_json(
            frame("user.barge_in", response_id=ack[0]["response_id"], heard_text="Looking")
        )
        send_user(ws, "cancel", "in_cancel")
        assert "Cancelled." in output(receive_until(ws, "response.done"))
        assert worker.cancelled.wait(2)


def test_connection_close_cancels_worker_and_clears_state(logic, monkeypatch):
    worker = Worker()
    monkeypatch.setattr(logic, "run_worker", worker)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client:
        with client.websocket_connect("/voice_conversation_engine") as ws:
            start(ws)
            send_user(ws, "search Quincy North")
            receive_until(ws, "response.output_text.delta")
            assert worker.started.wait(2)
        assert worker.cancelled.wait(2)
    assert app.state.voice_runtime._conversations == {}
    assert app.state.voice_runtime._store.drain() == ()


def test_concurrent_sessions_do_not_share_tasks(logic, monkeypatch):
    worker = Worker()
    monkeypatch.setattr(logic, "run_worker", worker)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client:
        with client.websocket_connect("/voice_conversation_engine") as first:
            start(first)
            send_user(first, "search private-site")
            receive_until(first, "response.output_text.delta")
            assert worker.started.wait(2)
            with client.websocket_connect("/voice_conversation_engine") as second:
                start(second)
                send_user(second, "hello")
                # This completes even while the first session's worker is blocked.
                assert output(receive_until(second, "response.done")) == "hello"
            assert not worker.cancelled.is_set()
            worker.release.set()
            assert "private-site" in output(receive_until(first, "response.done"))


def test_heard_text_replaces_unheard_output_in_history(logic, monkeypatch):
    observed = []
    previous = logic._iter_llm_stream

    async def router(*args, **kwargs):
        observed.append(args[3])
        async for event in previous(*args, **kwargs):
            yield event

    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, "A long answer that was not fully heard.")
        events = receive_until(ws, "response.done")
        ws.send_json(
            frame("user.barge_in", response_id=events[0]["response_id"], heard_text="A long")
        )
        send_user(ws, "next", "in_2")
        receive_until(ws, "response.done")
    assistant = [m["content"] for m in observed[-1] if m["role"] == "assistant"]
    assert assistant == ["A long"]


def test_duplicate_input_is_not_executed_twice(logic):
    app = create_app(handler=logic.handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send_user(ws, "first")
        receive_until(ws, "response.done")
        send_user(ws, "duplicate")
        send_user(ws, "second", "in_2")
        events = receive_until(ws, "response.done")
        assert output(events) == "second"
        assert events[0]["in_reply_to"] == ["in_2"]


def test_protocol_mismatch_rejected(logic):
    with TestClient(create_app(handler=logic.handler, configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as ws:
            assert start(ws, "2.0")["type"] == "session.rejected"


def test_repeated_no_input_drains_call(logic):
    with TestClient(create_app(handler=logic.handler, configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as ws:
            start(ws)
            ws.send_json(frame("user.no_input", item_id="in_idle", count=3))
            assert ws.receive_json()["type"] == "end_call"


class DeclineHostSocket:
    """Gate one outbound decline while the real SDK keeps receiving frames."""

    def __init__(self) -> None:
        self.scope: dict[str, Any] = {}
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames: list[dict[str, Any]] = []
        self.changed = asyncio.Event()
        self.none_started = asyncio.Event()
        self.release_none = asyncio.Event()

    def enqueue(self, kind: str, **fields: Any) -> None:
        self.incoming.put_nowait(
            {"type": "websocket.receive", "text": json.dumps(frame(kind, **fields))}
        )

    async def receive(self) -> dict[str, Any]:
        return await self.incoming.get()

    async def send_text(self, text: str) -> None:
        event = json.loads(text)
        if event["type"] == "response.none":
            self.none_started.set()
            await self.release_none.wait()
        self.frames.append(event)
        self.changed.set()


def _create_decline_app() -> Any:
    async def echo(request: Any, context: Any, signal: Any) -> Any:
        del context, signal
        yield {"type": "response.output_text.delta", "delta": request["input"]}

    return create_app(handler=echo, configure_observability=None)


def _enqueue_decline_start(socket: DeclineHostSocket) -> None:
    socket.enqueue(
        "session.start",
        protocol_version="1.0",
        reconnect=False,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30000},
    )


async def _wait_for_decline_event(socket: DeclineHostSocket, condition: Any) -> None:
    async with asyncio.timeout(2):
        while not condition():
            socket.changed.clear()
            await socket.changed.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["1.0", "2.0"])
async def test_reconnect_is_rejected_before_application_readiness(version):
    from azure.ai.agentserver.invocations.voice import Session

    from state import SessionPhase

    calls = []

    async def handler(request, _context, _signal):
        calls.append(request)
        yield {"type": "response.output_text.delta", "delta": "must not run"}

    app = create_app(handler=handler, configure_observability=None)
    runtime = app.state.voice_runtime
    socket = DeclineHostSocket()
    socket.enqueue(
        "session.start", protocol_version=version, reconnect=True,
        response_timeouts={"first_output_ms": 1000, "idle_ms": 1000, "max_duration_ms": 30000},
    )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await _wait_for_decline_event(socket, lambda: bool(socket.frames))
        rejection = socket.frames[0]
        assert rejection["type"] == "session.rejected"
        assert rejection["code"] == (
            "startup_failed" if version == "1.0" else "protocol_mismatch"
        )
        assert rejection["retriable"] is False
        state = runtime._store.get_or_create(Session._current(socket))
        assert state.phase is SessionPhase.REJECTED
        assert runtime._conversations == {}
        assert not state.responses

        socket.enqueue(
            "user.message", item_id="in_rejected", content=[{"type": "input_text", "text": "late"}]
        )
        # A second start cannot turn a rejected connection into a fresh conversation.
        _enqueue_decline_start(socket)
        socket.enqueue("user.no_input", item_id="in_idle", count=3)
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        assert socket.frames == [rejection]
        assert not calls
        assert runtime._conversations == {}
        assert not runtime._store._states
    finally:
        if not connection.done():
            socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.asyncio
async def test_disconnect_after_committed_turn_does_not_resume_with_empty_history():
    from azure.ai.agentserver.invocations.voice import Session

    from voice_runtime import VoiceRuntime

    calls = []

    async def handler(request, context, _signal):
        calls.append(context.history)
        yield {"type": "response.output_text.delta", "delta": request["input"]}

    runtime = VoiceRuntime(handler)
    first_socket, reconnect_socket = DeclineHostSocket(), DeclineHostSocket()
    first_socket.scope["agent_session_id"] = "same-logical-call"
    reconnect_socket.scope["agent_session_id"] = "same-logical-call"
    first, reconnected = Session._create(first_socket), Session._create(reconnect_socket)
    try:
        await runtime.on_session_start(
            first, SimpleNamespace(protocol_version="1.0", reconnect=False)
        )
        assert first_socket.frames[0]["type"] == "session.ready"
        await runtime.on_user_message(
            first,
            SimpleNamespace(item_id="in_committed", content=[InputTextPart(text="remember me")]),
        )
        state = runtime._store.active(first)
        assert state is not None
        await asyncio.gather(*(operation.task for operation in tuple(state.responses.values())))
        assert len(runtime._conversations[first].history) == 2
        assert first_socket.frames[-1]["type"] == "response.done"

        runtime.on_connection_terminating(first)
        await runtime._coordinator.wait_for_detached_tasks()
        assert runtime._conversations == {}
        await runtime.on_session_start(
            reconnected, SimpleNamespace(protocol_version="1.0", reconnect=True)
        )
        assert [event["type"] for event in reconnect_socket.frames] == ["session.rejected"]
        assert reconnect_socket.frames[0]["retriable"] is False
        assert reconnected not in runtime._conversations
        assert runtime._store.active(reconnected) is None
        await runtime.on_user_message(
            reconnected,
            SimpleNamespace(item_id="in_late", content=[InputTextPart(text="continue")]),
        )
        assert len(calls) == 1
        assert len(reconnect_socket.frames) == 1
    finally:
        await runtime.close()
    assert not runtime._store._states
    assert not runtime._conversations


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["response.timeout", "user.speech_started", "session.end"])
async def test_decline_backpressure_keeps_control_callbacks_responsive(kind: str) -> None:
    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    handled = asyncio.Event()
    callback = app._voice_callbacks[kind]

    async def observe(session: Any, event: Any) -> None:
        handled.set()
        await callback(session, event)

    app._voice_callbacks[kind] = observe
    _enqueue_decline_start(socket)
    socket.enqueue("user.message", item_id="in_empty", content=[{"type": "input_text", "text": ""}])
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(socket.none_started.wait(), 2)
        fields: dict[str, Any] = {}
        if kind == "response.timeout":
            fields = {"stage": "first_output", "item_ids": ["in_empty"]}
        elif kind == "session.end":
            fields = {"reason": "test_complete"}
        socket.enqueue(kind, **fields)
        await asyncio.wait_for(handled.wait(), 2)
        assert not socket.release_none.is_set()
    finally:
        socket.release_none.set()
        if not connection.done():
            socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.asyncio
async def test_cancelled_resolution_cannot_release_a_later_input_early() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    timeout_handled = asyncio.Event()
    callback = app._voice_callbacks["response.timeout"]

    async def observe(session: Any, event: Any) -> None:
        await callback(session, event)
        timeout_handled.set()

    app._voice_callbacks["response.timeout"] = observe
    _enqueue_decline_start(socket)
    for item_id, text in [("in_first", ""), ("in_cancel", "unused"), ("in_last", "last")]:
        socket.enqueue(
            "user.message", item_id=item_id, content=[{"type": "input_text", "text": text}]
        )
    connection = asyncio.create_task(app._handle_voice_connection(socket))
    try:
        await asyncio.wait_for(socket.none_started.wait(), 2)
        socket.enqueue("response.timeout", stage="first_output", item_ids=["in_cancel"])
        await asyncio.wait_for(timeout_handled.wait(), 2)
        state = runtime._store.active(Session._current(socket))
        assert state is not None
        await asyncio.sleep(0)
        assert not any("in_reply_to" in event for event in socket.frames)
        socket.release_none.set()
        await _wait_for_decline_event(
            socket,
            lambda: any(event["type"] == "response.done" for event in socket.frames)
        )
        resolved = [item for event in socket.frames for item in event.get("in_reply_to", [])]
        assert resolved == ["in_first", "in_last"]
    finally:
        socket.release_none.set()
        socket.enqueue("session.end", reason="test_complete")
        await asyncio.wait_for(connection, 2)
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_queued", [False, True])
async def test_pending_declines_are_bounded_and_drained(cancel_queued: bool) -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from state import MAX_PENDING_DECLINES

    socket = DeclineHostSocket()
    app = _create_decline_app()
    runtime = app.state.voice_runtime
    session = Session._create(socket)
    await runtime.on_session_start(
        session, SimpleNamespace(protocol_version="1.0", reconnect=False)
    )
    state = runtime._store.active(session)
    assert state is not None
    try:
        for index in range(MAX_PENDING_DECLINES):
            await runtime.on_user_message(
                session,
                SimpleNamespace(item_id=f"in_decline_{index}", content=[InputTextPart(text="")]),
            )
        if cancel_queued:
            await asyncio.wait_for(socket.none_started.wait(), 2)
            tasks = []
            for index in range(1, MAX_PENDING_DECLINES):
                operation = state.responses[state.input_responses[f"in_decline_{index}"]]
                tasks.append(operation.task)
                runtime._coordinator.response_timeout(state, None, [f"in_decline_{index}"])
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)
        assert state.pending_decline_count == MAX_PENDING_DECLINES
        assert state.active_response_count == 0
        with pytest.raises(RuntimeError, match="capacity exceeded"):
            await runtime.on_user_message(
                session,
                SimpleNamespace(item_id="in_overflow", content=[InputTextPart(text="")]),
            )
    finally:
        socket.release_none.set()
        await runtime.close()
    assert not state.responses
    assert not state.input_responses
    assert state.input_resolution_tail is not None
    await asyncio.wait_for(asyncio.shield(state.input_resolution_tail), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_event", ["barge_in", "cancelled", "timeout"])
@pytest.mark.parametrize("detached", [False, True])
async def test_repeated_cancellation_and_session_end_drain_async_cleanup(
    first_event: str, detached: bool
) -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    socket = DeclineHostSocket()
    session = Session._create(socket)
    coordinator = ResponseCoordinator()
    started = asyncio.Event()
    cleanup_entered = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def source():
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_entered.set()
            await release_cleanup.wait()
            cleanup_finished.set()

    assert coordinator.start_response(session, state, "in_cleanup", source())
    operation = next(iter(state.responses.values()))
    termination = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        if first_event == "barge_in":
            coordinator.barge_in(state, operation.response_id, "heard")
        elif first_event == "cancelled":
            coordinator.response_cancelled(state, operation.response_id, "heard")
        else:
            coordinator.response_timeout(state, None, ["in_cleanup"])
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        coordinator.response_cancelled(state, operation.response_id, "heard")
        coordinator.response_timeout(state, operation.response_id, None)
        assert state.active_response_count == 1
        assert state.input_responses["in_cleanup"] == operation.response_id
        if detached:
            coordinator.detach_terminating_state(state, OperationOutcome.TRANSPORT_ERROR)
            termination = asyncio.create_task(coordinator.wait_for_detached_tasks())
        else:
            termination = asyncio.create_task(
                coordinator.terminate_state(state, OperationOutcome.END_CALL)
            )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not termination.done()
        assert operation.task is not None
        assert operation.task.cancelling() == 1
        assert not cleanup_finished.is_set()
    finally:
        release_cleanup.set()
        if termination is not None:
            await asyncio.wait_for(termination, 2)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    assert cleanup_finished.is_set()
    assert not state.responses
    assert not state.input_responses
    assert operation.outcome is (
        OperationOutcome.TIMEOUT if first_event == "timeout" else OperationOutcome.CANCELLED
    )
    assert not any(event["type"] == "response.done" for event in socket.frames)


@pytest.mark.asyncio
async def test_cancel_before_task_start_releases_correlations_without_running_source() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    socket = DeclineHostSocket()
    coordinator = ResponseCoordinator()
    source_started = False

    async def source():
        nonlocal source_started
        source_started = True
        yield "must not run"

    assert coordinator.start_response(Session._create(socket), state, "in_unstarted", source())
    operation = next(iter(state.responses.values()))
    coordinator.barge_in(state, operation.response_id, "")
    coordinator.response_timeout(state, None, ["in_unstarted"])
    await asyncio.wait_for(coordinator.terminate_state(state, OperationOutcome.END_CALL), 2)
    assert not source_started
    assert not socket.frames
    assert not state.responses
    assert not state.input_responses
    assert state.input_resolution_tail is not None and state.input_resolution_tail.done()


@pytest.mark.asyncio
async def test_cancelled_sources_retain_capacity_until_cleanup_finishes() -> None:
    from azure.ai.agentserver.invocations.voice import Session

    from response_coordinator import ResponseCoordinator
    from state import MAX_ACTIVE_RESPONSES, OperationOutcome, SessionState

    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    coordinator = ResponseCoordinator()
    session = Session._create(DeclineHostSocket())
    release_cleanup = asyncio.Event()
    cleanup_finished = []

    async def source(started, cleanup_entered):
        try:
            yield "first"
            started.set()
            await asyncio.Future()
        finally:
            cleanup_entered.set()
            await release_cleanup.wait()
            cleanup_finished.append(True)

    try:
        for index in range(MAX_ACTIVE_RESPONSES):
            started = asyncio.Event()
            entered = asyncio.Event()
            item_id = f"in_capacity_{index}"
            assert coordinator.start_response(session, state, item_id, source(started, entered))
            await asyncio.wait_for(started.wait(), 2)
            coordinator.response_timeout(state, None, [item_id])
            await asyncio.wait_for(entered.wait(), 2)
        assert state.active_response_count == MAX_ACTIVE_RESPONSES
        assert not coordinator.start_response(session, state, "in_overflow", "overflow")
        release_cleanup.set()
        await asyncio.wait_for(
            asyncio.gather(
                *(operation.task for operation in tuple(state.responses.values())),
                return_exceptions=True,
            ),
            2,
        )
        await asyncio.sleep(0)
        assert len(cleanup_finished) == MAX_ACTIVE_RESPONSES
        assert not state.input_responses
        assert coordinator.start_response(session, state, "in_recovered", "recovered")
        await asyncio.gather(*(operation.task for operation in tuple(state.responses.values())))
    finally:
        release_cleanup.set()
        await asyncio.wait_for(coordinator.terminate_state(state, OperationOutcome.END_CALL), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_point",
    ["source", "source_close", "created_send", "self_cancel_send", "decline_send", "error_send"],
)
async def test_upstream_exception_content_is_not_logged(failure_point, caplog) -> None:
    import logging
    import time

    from response_coordinator import ResponseCoordinator
    from state import InputOrigin, OperationOutcome, SessionState

    marker = "SYNTHETIC_CUSTOMER_PROMPT_AND_CREDENTIAL_DO_NOT_LOG"
    caplog.set_level(logging.DEBUG, logger="voice_live_bridge")

    def fail():
        raise RuntimeError(marker) from ValueError("nested_" + marker)

    class FailingSession:
        async def send(self, event):
            failure_type = {
                "created_send": "response.created",
                "self_cancel_send": "response.cancel",
                "decline_send": "response.none",
                "error_send": "error",
            }.get(failure_point)
            if event.type == failure_type:
                fail()

    async def source():
        try:
            yield "first"
            if failure_point in {"source", "error_send"}:
                fail()
        finally:
            if failure_point == "source_close":
                fail()

    coordinator = ResponseCoordinator()
    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    session = FailingSession()
    try:
        if failure_point == "self_cancel_send":
            assert coordinator.start_self_cancel(
                session, state, "in_private", "text", time.monotonic()
            )
        elif failure_point == "decline_send":
            coordinator.schedule_none(
                session, state, "in_private", InputOrigin.USER, reason="no_reply_needed"
            )
        else:
            assert coordinator.start_response(
                session, state, "in_private", source(), time.monotonic()
            )
        operations = tuple(state.responses.values())
        await asyncio.wait_for(
            asyncio.gather(*(operation.task for operation in operations)), 2
        )
        records = [record for record in caplog.records if record.name == "voice_live_bridge"]
        assert records, "Failures must still produce a diagnostic."
        for record in records:
            assert marker not in record.getMessage()
            assert marker not in repr(record.args)
            assert record.exc_info is None
            assert not record.stack_info
        assert any("RuntimeError" in record.getMessage() for record in records)
        assert operations[0].outcome is OperationOutcome.ERROR
    finally:
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
