# Copyright (c) Microsoft. All rights reserved.

"""Application-data passthrough over the actual typed CE WebSocket route."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from test_voice_runtime import (
    RecordingSession,
    active_state,
    frame,
    receive_until,
    send_user,
    start,
)

from main import create_app
from response_coordinator import MAX_DATA_BYTES, ResponseCoordinator
from scripts.smoke_test import ResponseValidator
from scripts.smoke_test import main as smoke_main
from state import OperationOutcome


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"customer_id": "demo", "locale": "zh-CN"},
        pytest.param({"v": [1234567] * 8000}, id="dense-numeric-array"),
        {"type": "customer.context", "data": {"values": [None, False, 0, 1.25, "  你好 👋\n"]}},
    ],
)
def test_data_is_returned_verbatim_without_text_and_next_text_turn_works(data: dict) -> None:
    with TestClient(create_app(configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as ws:
            assert start(ws)["type"] == "session.ready"
            previous_response = previous_item = ""
            for index in range(2):
                ws.send_json(
                    frame(
                        "user.message",
                        item_id=f"in_data_{index}",
                        content=[{"type": "input_data", "data": data}],
                    )
                )
                frames = receive_until(ws, "response.done")
                assert [event["type"] for event in frames] == [
                    "response.created",
                    "response.output_data.done",
                    "response.done",
                ]
                assert frames[0]["in_reply_to"] == [f"in_data_{index}"]
                assert all(event["response_id"] == frames[0]["response_id"] for event in frames)
                assert json.dumps(frames[1]["data"], sort_keys=True) == json.dumps(
                    data, sort_keys=True
                )
                if index:
                    assert frames[0]["response_id"] != previous_response
                    assert frames[1]["item_id"] != previous_item
                previous_response, previous_item = frames[0]["response_id"], frames[1]["item_id"]
                validator = ResponseValidator(data)
                assert not validator.consume(frames[0])
                assert not validator.consume(frames[1])
                assert validator.consume(frames[2])
            send_user(ws, "in_text_after_data", "Hello")
            assert any(
                event["type"] == "response.output_text.done"
                for event in receive_until(ws, "response.done")
            )


@pytest.mark.parametrize("raw", ["null", "[]", '"text"', "0"])
def test_data_cli_rejects_non_objects_before_connecting(raw: str, monkeypatch: Any) -> None:
    monkeypatch.setattr("sys.argv", ["smoke_test.py", "--data", raw])
    with pytest.raises(SystemExit) as error:
        smoke_main()
    assert error.value.code == 2


async def test_text_items_close_before_data_and_all_items_keep_wire_order() -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()

    async def source() -> AsyncIterator[str | dict]:
        yield {"position": 0}
        yield "first"
        yield " text"
        yield {"position": 1}
        yield "last"

    assert coordinator.send_echo(session, state, "in_mixed", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(operation.task, timeout=2)
    assert [event.type for event in session.sent] == [
        "response.created",
        "response.output_data.done",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.done",
        "response.output_data.done",
        "response.output_text.delta",
        "response.output_text.done",
        "response.done",
    ]
    assert session.sent[4].text == "first text"
    assert session.sent[7].text == "last"
    assert operation.output_item_count == 4
    done_items = [
        event.item_id
        for event in session.sent
        if event.type.endswith(("output_data.done", "output_text.done"))
    ]
    assert len(set(done_items)) == 4


@pytest.mark.parametrize("failure", ["timeout", "end_call", "send_error", "source_error"])
async def test_data_operation_keeps_cancellation_and_producer_cleanup(failure: str) -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    waiting = asyncio.Event()
    closed = asyncio.Event()

    class Session(RecordingSession):
        async def send(self, event: Any) -> None:
            if failure == "send_error" and event.type == "response.output_data.done":
                raise RuntimeError("Controlled send failure")
            await super().send(event)

    session = Session()

    async def source() -> AsyncIterator[dict]:
        try:
            yield {"status": "progress"}
            waiting.set()
            if failure == "source_error":
                raise RuntimeError("Controlled source failure")
            await asyncio.Future()
        finally:
            await asyncio.sleep(0)
            closed.set()

    assert coordinator.send_echo(session, state, "in_cleanup", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    if failure in {"timeout", "end_call"}:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        if failure == "timeout":
            coordinator.response_timeout(state, None, ["in_cleanup"])
            coordinator.response_timeout(state, None, ["in_cleanup"])
        else:
            await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), timeout=2)
    await asyncio.sleep(0)
    assert closed.is_set()
    assert not state.responses and not state.input_responses
    assert not any(event.type == "response.done" for event in session.sent)
    if failure in {"send_error", "source_error"}:
        assert session.sent[-1].type == "error"


@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
async def test_data_utf8_byte_budget(extra_bytes: int) -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    overhead = len(json.dumps({"value": ""}, separators=(",", ":")).encode("utf-8"))
    budget = MAX_DATA_BYTES - overhead + extra_bytes
    data = {"value": "👋" * (budget // 4) + "x" * (budget % 4)}
    assert coordinator.start_response(session, state, "in_budget", data)
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(operation.task, timeout=2)
    if extra_bytes > 0:
        assert [event.type for event in session.sent] == ["response.created", "error"]
    else:
        assert [event.type for event in session.sent] == [
            "response.created",
            "response.output_data.done",
            "response.done",
        ]
