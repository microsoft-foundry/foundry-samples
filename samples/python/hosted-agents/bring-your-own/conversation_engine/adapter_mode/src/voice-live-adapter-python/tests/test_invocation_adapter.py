# Copyright (c) Microsoft. All rights reserved.

"""Exercise the actual HTTP-shaped handler and its in-process stream lifecycle."""

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from azure.ai.agentserver.invocations.voice import InputDataPart
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient
from test_voice_runtime import frame, receive_until, send_user, start

from adapter import invocation
from adapter.invocation import InvocationAdapter, invocation_request
from adapter.runtime import create_app
from echo_agent import handle_invocation


def event(kind: str, **fields: Any) -> str:
    return "data: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"


def boundary_data(character: str, extra_bytes: int) -> dict[str, str]:
    overhead = len(json.dumps({"value": ""}).encode("utf-8"))
    unit_bytes = len(json.dumps(character, ensure_ascii=False).encode("utf-8")) - 2
    count, remainder = divmod(invocation.MAX_DATA_BYTES - overhead + extra_bytes, unit_bytes)
    data = {"value": character * count + "x" * remainder}
    assert len(json.dumps(data, ensure_ascii=False).encode("utf-8")) == (
        invocation.MAX_DATA_BYTES + extra_bytes
    )
    return data


@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
@pytest.mark.parametrize("character", ["x", "界", "👋", "\n", '"', "\\"])
async def test_handler_adapter_data_byte_boundary(character: str, extra_bytes: int) -> None:
    data = boundary_data(character, extra_bytes)
    stream = InvocationAdapter(handle_invocation).stream(
        InputDataPart(data=data).data, "in_boundary"
    )
    if extra_bytes > 0:
        with pytest.raises(ValueError, match="Invocation data exceeds its byte budget"):
            _ = [chunk async for chunk in stream]
    else:
        assert [chunk async for chunk in stream] == [data]


@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_data_boundary_over_ce_socket_and_recovery(extra_bytes: int) -> None:
    data = boundary_data("x", extra_bytes)
    with TestClient(create_app(handle_invocation, configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as socket:
            assert start(socket)["type"] == "session.ready"
            socket.send_json(
                frame(
                    "user.message",
                    item_id="in_boundary",
                    content=[{"type": "input_data", "data": data}],
                )
            )
            created = socket.receive_json()
            assert created["type"] == "response.created"
            assert created["in_reply_to"] == ["in_boundary"]
            output = socket.receive_json()
            assert output["response_id"] == created["response_id"]
            if extra_bytes > 0:
                assert output["type"] == "error"
            else:
                assert output["type"] == "response.output_data.done"
                assert output["data"] == data
                done = socket.receive_json()
                assert done["type"] == "response.done"
                assert done["response_id"] == created["response_id"]
            send_user(socket, "in_recovery", "ok")
            frames = receive_until(socket, "response.done")
            assert frames[0]["in_reply_to"] == ["in_recovery"]
            assert frames[-2]["type"] == "response.output_text.done"
            assert frames[-2]["text"] == "ok"


@pytest.mark.parametrize("terminated", [False, True])
async def test_sse_frame_budget_bounds_complete_and_incomplete_frames(terminated: bool) -> None:
    async def chunks() -> AsyncIterator[str]:
        yield "data: " + "x" * invocation.MAX_FRAME_CHARACTERS + ("\n\n" if terminated else "")

    with pytest.raises(ValueError, match="frame exceeds its character budget"):
        _ = [message async for message in invocation.sse_events(chunks())]


@pytest.mark.parametrize(
    "data", [{}, {"type": "customer.context", "data": {"values": [None, False, 0, "你好 👋"]}}]
)
async def test_frozen_json_input_reaches_handler_and_returns_complete_object(data: dict) -> None:
    received = []

    async def handler(request: Any) -> StreamingResponse:
        received.append(await request.json())
        return await handle_invocation(request)

    result = [
        chunk async for chunk in InvocationAdapter(handler).stream(
            InputDataPart(data=data).data, "in_json"
        )
    ]
    assert received == [{"input": data}]
    assert result == [data]
    assert json.dumps(result[0], sort_keys=True) == json.dumps(data, sort_keys=True)


async def test_sse_keeps_text_and_data_in_order() -> None:
    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            yield event("token", content="before")
            yield event("data", data={"type": "business.event", "data": {"value": 1}})
            yield event("token", content=" after")
            yield event("done", full_text="before after")

        return StreamingResponse(chunks(), media_type="text/event-stream")

    assert [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_mixed")] == [
        "before", {"type": "business.event", "data": {"value": 1}}, " after"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Hello world",
        "  你好 👋\n",
        "/end",
        " \t ",
        pytest.param("👋" * 6_000, id="emoji-reported-reproduction"),
        pytest.param("👋" * 8_000, id="emoji-at-input-limit"),
        pytest.param("👋" * 3_000 + " " + "👋" * 3_000, id="emoji-completion-frame"),
        pytest.param("界" * 8_000, id="cjk-at-input-limit"),
    ],
)
async def test_plain_http_handler_and_adapter_echo_without_a_server(text: str) -> None:
    response = await handle_invocation(invocation_request(text, "in_echo"))
    assert response.media_type == "text/event-stream"
    # This is the handler's HTTP response, not a Voice or SDK message stream.
    raw = "".join([chunk async for chunk in response.body_iterator])
    assert '"type": "token"' in raw
    assert '"type": "done"' in raw
    assert all(
        len(frame) <= invocation.MAX_FRAME_CHARACTERS for frame in raw.split("\n\n") if frame
    )
    assert (
        "".join(
            [chunk async for chunk in InvocationAdapter(handle_invocation).stream(text, "in_echo")]
        )
        == text
    )


async def test_split_utf8_crlf_and_multiline_sse_are_decoded_incrementally() -> None:
    raw = (
        'data: {"type":"token",\r\ndata: "content":"你好 👋"}\r\n\r\n'
        + event("done", full_text="你好 👋")
    ).encode()

    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            for byte in raw:
                yield bytes([byte])

        return StreamingResponse(chunks(), media_type="text/event-stream")

    assert [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_utf8")] == [
        "你好 👋"
    ]


@pytest.mark.parametrize("kind", ["token", "data"])
async def test_first_chunk_precedes_later_work_and_close_disposes_the_source(kind: str) -> None:
    closed = False
    later_started = False

    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            nonlocal closed, later_started
            try:
                yield (
                    event("token", content="first") if kind == "token"
                    else event("data", data={"value": "first"})
                )
                later_started = True
                await asyncio.Future()
            finally:
                closed = True

        return StreamingResponse(chunks(), media_type="text/event-stream")

    stream = InvocationAdapter(handler).stream("input", "in_gated")
    assert await anext(stream) == ("first" if kind == "token" else {"value": "first"})
    assert not later_started
    await stream.aclose()
    assert closed


@pytest.mark.parametrize(
    "body",
    [
        event("token", content="hello"),
        "data: not-json\n\n",
        'data: {"type":"token"}',
        event("token", content=1),
        event("token", content=""),
        event("token", content="hello") + event("done", full_text="wrong"),
        event("done", full_text="") + event("done", full_text=""),
        event("unknown"),
        event("data", data=[]),
        event("data", data=None),
        event("data", data={"value": float("nan")}),
        event("done", full_text="") + event("data", data={}),
        "data: " + "x" * 65_537,
        event("token", content="x" * 8_001),
    ],
)
async def test_invalid_or_incomplete_sse_is_not_success(body: str) -> None:
    closed = False

    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            nonlocal closed
            try:
                yield body
            finally:
                closed = True

        return StreamingResponse(chunks(), media_type="text/event-stream")

    with pytest.raises(ValueError):
        _ = [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_invalid")]
    assert closed


@pytest.mark.parametrize(
    ("status", "media_type"), [(500, "text/event-stream"), (200, "application/json")]
)
@pytest.mark.parametrize("fail_close", [False, True])
async def test_failed_http_response_closes_body_before_background_cleanup(
    status: int, media_type: str, fail_close: bool
) -> None:
    cleanup_events = []

    class TrackedBody:
        def __aiter__(self) -> AsyncIterator[str]:
            return self

        async def __anext__(self) -> str:
            pytest.fail("Rejected response bodies must not be read")

        async def aclose(self) -> None:
            cleanup_events.append("body")
            if fail_close:
                raise RuntimeError("Controlled body close failure")

    async def cleanup() -> None:
        cleanup_events.append("background")

    async def handler(_request: Any) -> StreamingResponse:
        return StreamingResponse(
            TrackedBody(),
            status_code=status,
            media_type=media_type,
            background=BackgroundTask(cleanup),
        )

    with pytest.raises(RuntimeError if fail_close else ValueError):
        _ = [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_error")]
    assert cleanup_events == ["body", "background"]


async def test_completion_waits_for_handler_finalization_and_background_work() -> None:
    finalized = False
    background_ran = False

    async def background() -> None:
        nonlocal background_ran
        await asyncio.sleep(0)
        background_ran = True

    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            nonlocal finalized
            yield event("token", content="hello")
            yield event("done", full_text="hello")
            await asyncio.sleep(0)
            finalized = True

        return StreamingResponse(
            chunks(), media_type="text/event-stream", background=BackgroundTask(background)
        )

    assert [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_final")] == [
        "hello"
    ]
    assert finalized and background_ran


@pytest.mark.parametrize("kind", ["token", "data"])
def test_state_save_failure_after_done_never_emits_a_success_terminal(kind: str) -> None:
    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            yield (
                event("token", content="hello") if kind == "token"
                else event("data", data={"value": "hello"})
            )
            yield event("done", full_text="hello" if kind == "token" else "")
            raise ValueError("controlled finalization failure")

        return StreamingResponse(chunks(), media_type="text/event-stream")

    with TestClient(create_app(handler, configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as socket:
            socket.send_json(
                {
                    "type": "session.start",
                    "id": "m_start",
                    "ts": "2026-10-29T00:00:00Z",
                    "protocol_version": "1.0",
                    "reconnect": False,
                    "response_timeouts": {
                        "first_output_ms": 30_000,
                        "idle_ms": 30_000,
                        "max_duration_ms": 120_000,
                    },
                }
            )
            assert socket.receive_json()["type"] == "session.ready"
            socket.send_json(
                {
                    "type": "user.message",
                    "id": "m_user",
                    "ts": "2026-10-29T00:00:01Z",
                    "item_id": "in_save",
                    "content": [{"type": "input_text", "text": "input"}],
                }
            )
            created = socket.receive_json()
            assert created["type"] == "response.created"
            assert socket.receive_json()["type"] == (
                "response.output_text.delta" if kind == "token" else "response.output_data.done"
            )
            failed = socket.receive_json()
            assert failed["type"] == "error"
            assert failed["response_id"] == created["response_id"]


def test_request_context_is_from_the_sdk_not_input(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        invocation,
        "get_request_context",
        lambda: SimpleNamespace(
            session_id="trusted-session", user_id="trusted-user", call_id="trusted-call"
        ),
    )
    request = invocation_request('{"session_id":"forged"}', "in_context")
    assert request.state.session_id == "trusted-session"
    assert request.state.user_id == "trusted-user"
    assert request.state.call_id == "trusted-call"
    assert request.state.invocation_id == "in_context"
