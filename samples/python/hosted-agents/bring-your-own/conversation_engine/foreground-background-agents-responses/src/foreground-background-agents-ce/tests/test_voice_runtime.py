# Copyright (c) Microsoft. All rights reserved.

"""Real CE socket tests with only the original handler's model/worker calls replaced."""

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace

import pytest
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
