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


@pytest.mark.parametrize("binary", [False, True])
@pytest.mark.parametrize("batched", [False, True])
async def test_large_valid_batches_are_not_limited_by_handler_write_boundaries(binary, batched):
    tokens = ['data: {"type":"token","content":"x"}\n\n'] * 8000
    done = 'data: ' + json.dumps({"type": "done", "full_text": "x" * 8000}) + '\n\n'
    chunks = ["".join(tokens[:7000]), *tokens[7000:], done] if batched else [*tokens, done]

    async def handler(_request):
        async def body():
            for chunk in chunks:
                yield chunk.encode() if binary else chunk

        return StreamingResponse(body(), media_type="text/event-stream")

    output = [part async for part in InvocationAdapter(handler).stream("input", "in_batch")]
    assert "".join(output) == "x" * 8000


async def test_one_leading_utf8_bom_is_ignored_even_when_split_into_bytes():
    token = {"type": "token", "content": "\ufeff你好 👋"}
    raw = b"\xef\xbb\xbf" + ("data: " + json.dumps(token, ensure_ascii=False) + "\n\n").encode()
    assert await parse([raw]) == [token]
    for split in range(len(raw) + 1):
        assert await parse([raw[:split], b"", raw[split:]]) == [token]
    assert await parse([bytes([value]) for value in raw]) == [token]
    # Only a single BOM at the very start is special.
    assert await parse([b"\xef\xbb\xbf" + raw]) == []


@pytest.mark.parametrize("media_type, accepted", [
    ("text/event-stream", True),
    ("Text/Event-Stream; charset=utf-8", True),
    ("TEXT/EVENT-STREAM", True),
    ("text/event-stream-invalid", False),
    ("text/event-streaming; charset=utf-8", False),
])
async def test_sse_media_type_uses_exact_case_insensitive_token(media_type, accepted):
    async def handler(_request):
        async def body():
            yield 'data: {"type":"token","content":"x"}\n\n'
            yield 'data: {"type":"done","full_text":"x"}\n\n'

        return StreamingResponse(body(), headers={"content-type": media_type})

    source = InvocationAdapter(handler).stream("input", "in_media")
    if accepted:
        assert [chunk async for chunk in source] == ["x"]
    else:
        with pytest.raises(ValueError, match="Expected an SSE response"):
            _ = [chunk async for chunk in source]
