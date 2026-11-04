# Copyright (c) Microsoft. All rights reserved.

"""SSE acceptance must depend on content, not transport chunk boundaries."""

import json

import pytest
from starlette.responses import StreamingResponse

from adapter.invocation import MAX_FRAME_CHARACTERS, InvocationAdapter, sse_events


async def parse(chunks):
    async def source():
        for chunk in chunks:
            yield chunk

    return [event async for event in sse_events(source())]


@pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
async def test_every_byte_split_preserves_sse_newlines_and_utf8(ending):
    token = {"type": "token", "content": "你好 👋"}
    done = {"type": "done", "full_text": "你好 👋"}
    raw = (
        ": heartbeat" + ending * 2
        + "data: " + json.dumps(token, ensure_ascii=False) + ending * 2
        + "data: " + json.dumps(done, ensure_ascii=False) + ending * 2
    ).encode()
    for split in range(len(raw) + 1):
        # Empty and partial UTF-8 chunks must not lose pending CRLF state.
        assert await parse([raw[:split], b"", raw[split:]]) == [token, done]
    assert await parse([bytes([value]) for value in raw]) == [token, done]


async def test_mixed_line_endings_and_multiline_data():
    raw = b'data: {"type":"token",\rdata: "content":"ok"}\n\r\n'
    assert await parse([bytes([value]) for value in raw]) == [{"type": "token", "content": "ok"}]


@pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
async def test_complete_handler_adapter_stream_accepts_all_sse_line_endings(ending):
    async def handler(_request):
        async def chunks():
            for event in [{"type": "token", "content": "你好 👋"},
                          {"type": "done", "full_text": "你好 👋"}]:
                raw = ("data: " + json.dumps(event, ensure_ascii=False) + ending * 2).encode()
                for value in raw:
                    yield bytes([value])

        return StreamingResponse(chunks(), media_type="text/event-stream")

    assert [chunk async for chunk in InvocationAdapter(handler).stream("input", "in_sse")] == [
        "你好 👋"
    ]


@pytest.mark.parametrize("extra", [-1, 0, 1])
@pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
async def test_frame_content_budget_is_independent_of_split_delimiters(extra, ending):
    empty = "data: " + json.dumps({"type": "token", "content": "ok", "pad": ""})
    event = {"type": "token", "content": "ok", "pad": "x" * (
        MAX_FRAME_CHARACTERS + extra - len(empty)
    )}
    frame = ("data: " + json.dumps(event)).encode()
    assert len(frame) == MAX_FRAME_CHARACTERS + extra
    raw = frame + (ending * 2).encode()
    for split in range(len(frame) - 1, len(raw) + 1):
        chunks = [raw[:split], b"", raw[split:]]
        if extra > 0:
            with pytest.raises(ValueError, match="frame exceeds"):
                await parse(chunks)
        else:
            assert await parse(chunks) == [event]


def test_collected_ids_fit_windows_environment_variables(request):
    assert all(len(item.nodeid) < 32_000 for item in request.session.items)
