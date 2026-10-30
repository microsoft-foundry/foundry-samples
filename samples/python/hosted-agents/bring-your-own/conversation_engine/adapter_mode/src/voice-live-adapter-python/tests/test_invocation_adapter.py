# Copyright (c) Microsoft. All rights reserved.

"""Exercise the actual HTTP-shaped handler and its in-process stream lifecycle."""

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient

from adapter import invocation
from adapter.invocation import InvocationAdapter, invocation_request
from adapter.runtime import create_app
from echo_agent import handle_invocation


def event(kind: str, **fields: Any) -> str:
    return "data: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"


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


async def test_first_chunk_precedes_later_work_and_close_disposes_the_source() -> None:
    closed = False
    later_started = False

    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            nonlocal closed, later_started
            try:
                yield event("token", content="first")
                later_started = True
                await asyncio.Future()
            finally:
                closed = True

        return StreamingResponse(chunks(), media_type="text/event-stream")

    stream = InvocationAdapter(handler).stream("input", "in_gated")
    assert await anext(stream) == "first"
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
async def test_failed_http_response_runs_background_cleanup(status: int, media_type: str) -> None:
    cleaned = False

    async def cleanup() -> None:
        nonlocal cleaned
        cleaned = True

    async def handler(_request: Any) -> StreamingResponse:
        return StreamingResponse(
            iter([]), status_code=status, media_type=media_type, background=BackgroundTask(cleanup)
        )

    with pytest.raises(ValueError):
        _ = [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_error")]
    assert cleaned


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


def test_state_save_failure_after_done_never_emits_a_success_terminal() -> None:
    async def handler(_request: Any) -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            yield event("token", content="hello")
            yield event("done", full_text="hello")
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
            assert socket.receive_json()["type"] == "response.output_text.delta"
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
