# Copyright (c) Microsoft. All rights reserved.

"""SSE framing is independent of producer writes, with bounded parsing work."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient
from test_voice_runtime import frame, receive_until, send_user, start

from adapter.invocation import InvocationAdapter, sse_events
from adapter.runtime import create_app as create_handler_app
from echo_agent import handle_invocation
from main import create_app

FRAME_BYTES = 512 * 1024


def event(kind: str, **fields: Any) -> str:
    return "data: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"


async def chunks(values: list[Any]) -> AsyncIterator[Any]:
    for value in values:
        yield value


async def collect(values: list[Any], content_type: str = "text/event-stream") -> list[Any]:
    async def handler(_request: Any) -> StreamingResponse:
        return StreamingResponse(chunks(values), headers={"content-type": content_type})

    return [value async for value in InvocationAdapter(handler).stream("input", "in_sse")]


@pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
async def test_every_two_part_split_preserves_utf8_lines_and_bom(ending: str, bom: str) -> None:
    raw = (
        bom + ': comment\nunknown: ignored\ndata: {"type":"token",\n'
        'data: "content":" 你好 👋 "}\n\n' + event("done", full_text=" 你好 👋 ")
    ).replace("\n", ending).encode()
    for split in range(len(raw) + 1):
        assert await collect([raw[:split], raw[split:]]) == [" 你好 👋 "]
    assert await collect([bytes([value]) for value in raw]) == [" 你好 👋 "]


@pytest.mark.parametrize("batch", [1, 7_000, 8_001])
async def test_eight_thousand_tokens_work_at_every_write_size(batch: int) -> None:
    frames = [event("token", content="x")] * 8_000 + [event("done", full_text="x" * 8_000)]
    writes = ["".join(frames[index:index + batch]) for index in range(0, len(frames), batch)]
    assert "".join(await collect(writes)) == "x" * 8_000


@pytest.mark.parametrize("content_type", [
    "text/event-stream", "Text/Event-Stream; charset=utf-8", "TEXT/EVENT-STREAM; x=y",
])
async def test_media_type_is_case_insensitive(content_type: str) -> None:
    assert await collect([event("token", content="x"), event("done", full_text="x")],
                         content_type) == ["x"]


@pytest.mark.parametrize("content_type", [
    "text/event-stream-invalid", "text/event-stream+json", "application/json", "",
])
async def test_bad_media_type_is_rejected_and_next_invocation_works(content_type: str) -> None:
    body = [event("token", content="x"), event("done", full_text="x")]
    with pytest.raises(ValueError):
        await collect(body, content_type)
    assert await collect(body) == ["x"]


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
async def test_normalized_utf8_event_budget_includes_comments(extra: int, bom: str) -> None:
    # Budget includes normalized LF delimiters, but not the optional stream BOM.
    comment = bom + ":" + "x" * (FRAME_BYTES - 3 + extra) + "\r\n\r\n"
    body = [comment, event("token", content="x"), event("done", full_text="x")]
    if extra:
        with pytest.raises(ValueError, match="budget"):
            await collect(body)
    else:
        assert await collect(body) == ["x"]
    assert await collect([event("token", content="ok"), event("done", full_text="ok")]) == ["ok"]


async def test_trailing_comment_is_not_a_truncated_event() -> None:
    assert await collect([event("token", content="x") + event("done", full_text="x")
                          + ": trailing comment"]) == ["x"]


@pytest.mark.parametrize("bad", [
    b'data: {"type":"token","content":"\xff"}\n\n',
    b'data: {"type":"token","content":"\xf0\x9f',
    b'data: {"type":"token","content":"x","extra":NaN}\n\n',
    b'data: {"type":"token","content":"x","extra":Infinity}\n\n',
    b'data: {"type":"token","content":"x"}',
])
async def test_invalid_encoding_json_and_truncation_are_not_completion(bad: bytes) -> None:
    with pytest.raises(ValueError):
        await collect([bad, event("done", full_text="x").encode()])
    assert await collect([event("token", content="ok"), event("done", full_text="ok")]) == ["ok"]


@pytest.mark.parametrize("mode", ["separate", "batched", "empty"])
async def test_ready_comment_stream_allows_control_callback_before_output(mode: str) -> None:
    control_ran = False

    def control() -> None:
        nonlocal control_ran
        control_ran = True

    asyncio.get_running_loop().call_soon(control)
    frames = ([""] if mode == "empty" else [": heartbeat\n\n"]) * 4_096
    frames.append(event("token", content="x"))
    values = ["".join(frames)] if mode == "batched" else frames
    async for parsed in sse_events(chunks(values)):
        assert control_ran
        assert parsed["content"] == "x"


@pytest.mark.parametrize("text", ["👋" * 8_000, "\x00" * 8_000, "你好 " * 2_000],
                         ids=["emoji", "control", "mixed"])
async def test_real_echo_accepts_valid_unicode_and_escaped_text(text: str) -> None:
    assert "".join([value async for value in InvocationAdapter(handle_invocation).stream(
        text, "in_unicode"
    )]) == text


@pytest.mark.parametrize("count", [8_000, 8_001])
def test_text_input_budget_uses_unicode_scalars_and_followup_works(count: int) -> None:
    text = "👋" * count
    with TestClient(create_app(configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as socket:
            assert start(socket)["type"] == "session.ready"
            send_user(socket, "in_unicode", text)
            received = []
            for _ in range(4):
                received.append(socket.receive_json())
                if received[-1]["type"] in {"response.none", "response.done", "error"}:
                    break
            if count == 8_000:
                assert received[-1]["type"] == "response.done"
                assert received[-2]["text"] == text
            else:
                assert received[0]["type"] == "response.none"
                assert received[0]["reason"] == "input_too_large"
            send_user(socket, "in_followup", "ok")
            assert receive_until(socket, "response.done")[-2]["text"] == "ok"


@pytest.mark.parametrize("character", ["x", "👋", "\x00", "\\", '"'])
@pytest.mark.parametrize("extra", [0, 1])
def test_json_budget_through_echo_adapter_sdk_and_next_turn(character: str, extra: int) -> None:
    empty_bytes = len(json.dumps({"value": ""}, separators=(",", ":")).encode())
    unit = len(json.dumps(character, ensure_ascii=False)[1:-1].encode())
    length = 65_536 - empty_bytes + extra
    data = {"value": character * (length // unit) + "x" * (length % unit)}
    assert len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()) == (
        65_536 + extra
    )
    with TestClient(create_app(configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as socket:
            assert start(socket)["type"] == "session.ready"
            socket.send_json(frame("user.message", item_id="in_boundary", content=[
                {"type": "input_data", "data": data},
            ]))
            received = []
            for _ in range(3):
                received.append(socket.receive_json())
                if received[-1]["type"] in {"error", "response.done"}:
                    break
            if extra:
                assert [value["type"] for value in received] == ["response.created", "error"]
            else:
                assert received[1]["type"] == "response.output_data.done"
                assert received[1]["data"] == data
            send_user(socket, "in_followup", "ok")
            assert receive_until(socket, "response.done")[-2]["text"] == "ok"


@pytest.mark.parametrize("parts", [1, 2])
@pytest.mark.parametrize("kind", ["text", "data"])
def test_response_budget_spans_handler_invocations_and_followup_works(
    parts: int, kind: str,
) -> None:
    async def handler(request: Any) -> StreamingResponse:
        value = (await request.json())["input"]
        if isinstance(value, dict) and kind == "data":
            frames = [event("data", data={"value": "x" * 33_000}), event("done", full_text="")]
        else:
            text = "x" * 5_000 if isinstance(value, dict) else value
            frames = [event("token", content=text), event("done", full_text=text)]
        return StreamingResponse(chunks(frames), media_type="text/event-stream")

    with TestClient(create_handler_app(handler, configure_observability=None)) as client:
        with client.websocket_connect("/voice_conversation_engine") as socket:
            assert start(socket)["type"] == "session.ready"
            socket.send_json(frame("user.message", item_id="in_multi", content=[
                {"type": "input_data", "data": {"part": index}} for index in range(parts)
            ]))
            received = []
            for _ in range(5):
                received.append(socket.receive_json())
                if received[-1]["type"] in {"error", "response.done"}:
                    break
            assert received[-1]["type"] == ("response.done" if parts == 1 else "error")
            if kind == "text":
                assert sum(len(value["delta"]) for value in received
                           if value["type"] == "response.output_text.delta") == 5_000
            else:
                assert sum(value["type"] == "response.output_data.done" for value in received) == 1
            send_user(socket, "in_followup", "ok")
            assert receive_until(socket, "response.done")[-2]["text"] == "ok"
