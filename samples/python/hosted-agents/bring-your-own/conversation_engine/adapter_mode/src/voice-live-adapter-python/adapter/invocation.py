# Copyright (c) Microsoft. All rights reserved.

"""Invoke an HTTP-shaped handler in process, without an HTTP server or client."""

import codecs
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from azure.ai.agentserver.core import get_request_context
from starlette.requests import Request
from starlette.responses import StreamingResponse

InvocationHandler = Callable[[Request], Awaitable[StreamingResponse]]
MAX_OUTPUT_CHARACTERS = 8_000
MAX_DATA_BYTES = 65_536
# The bounded SSE/JSON envelope is additional to the application-data byte budget.
MAX_FRAME_CHARACTERS = MAX_DATA_BYTES + len(
    "data: " + json.dumps({"type": "data", "data": {}})
)


def invocation_request(text: str | Mapping[str, Any], input_id: str) -> Request:
    """Supply only the current SDK context, not identity from caller JSON."""
    # InputDataPart deeply freezes objects; thaw mappings only for JSON encoding.
    body = json.dumps(
        {"input": text}, default=dict, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    context = get_request_context()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/invocations",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "state": {
                "session_id": context.session_id,
                "invocation_id": input_id,
                "user_id": context.user_id,
                "call_id": context.call_id,
            },
        },
        receive=receive,
    )


async def sse_events(chunks: AsyncIterator[Any]) -> AsyncIterator[dict[str, Any]]:
    """Parse bounded JSON SSE frames with incremental UTF-8 and universal newlines."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    buffer = ""
    skip_lf = False
    async for chunk in chunks:
        # Handler write boundaries are not frame boundaries. Decode bounded slices
        # while limiting individual frames, including a partial frame across writes.
        if not isinstance(chunk, str):
            chunk = memoryview(chunk)
        for offset in range(0, len(chunk), 4096):
            piece = chunk[offset : offset + 4096]
            encoded = piece.encode("utf-8") if isinstance(piece, str) else piece
            decoded = decoder.decode(encoded)
            if decoded:
                # CR ends a line immediately; swallow its optional LF across slices.
                previous_cr = decoded.endswith("\r")
                if skip_lf and decoded.startswith("\n"):
                    decoded = decoded[1:]
                skip_lf = previous_cr
                buffer += decoded.replace("\r\n", "\n").replace("\r", "\n")
            while "\n\n" in buffer:
                frame, _, buffer = buffer.partition("\n\n")
                if len(frame) > MAX_FRAME_CHARACTERS:
                    raise ValueError("SSE frame exceeds its character budget")
                data = [
                    line[5:].removeprefix(" ")
                    for line in frame.split("\n") if line.startswith("data:")
                ]
                if data:
                    event = json.loads("\n".join(data))
                    if not isinstance(event, dict):
                        raise ValueError("Expected a JSON SSE object")
                    yield event
            # A trailing newline may be the first half of the blank-line delimiter.
            if len(buffer.removesuffix("\n")) > MAX_FRAME_CHARACTERS:
                raise ValueError("SSE frame exceeds its character budget")
    buffer += decoder.decode(b"", final=True)
    if buffer.strip():
        raise ValueError("SSE ended inside a frame")


class InvocationAdapter:
    """Translate token/data/done SSE into ordered text and JSON output."""

    def __init__(self, handler: InvocationHandler) -> None:
        self._handler = handler

    async def stream(
        self, text: str | Mapping[str, Any], input_id: str
    ) -> AsyncIterator[str | dict[str, Any]]:
        response = await self._handler(invocation_request(text, input_id))
        iterator = None
        try:
            # Rejected responses must also close their streaming body.
            iterator = aiter(response.body_iterator)
            if not 200 <= response.status_code < 300:
                raise ValueError("Invocation failed")
            media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            if media_type.lower() != "text/event-stream":
                raise ValueError("Expected an SSE response")
            completed = False
            output = ""
            data_bytes = 0
            async for event in sse_events(iterator):
                if completed:
                    raise ValueError("SSE event after done")
                if event.get("type") == "token":
                    chunk = event.get("content")
                    if not isinstance(chunk, str) or not chunk:
                        raise ValueError("Expected a nonempty token")
                    if len(output) + len(chunk) > MAX_OUTPUT_CHARACTERS:
                        raise ValueError("Invocation output exceeds its character budget")
                    output += chunk
                    yield chunk
                elif event.get("type") == "data":
                    data = event.get("data")
                    if not isinstance(data, dict):
                        raise ValueError("Expected an application JSON object")
                    data_bytes += len(
                        json.dumps(
                            data, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                        ).encode("utf-8")
                    )
                    if data_bytes > MAX_DATA_BYTES:
                        raise ValueError("Invocation data exceeds its byte budget")
                    yield data
                elif event.get("type") == "done" and event.get("full_text") == output:
                    completed = True
                else:
                    raise ValueError("Invalid invocation SSE event")
            if not completed:
                raise ValueError("Invocation ended without done")
        finally:
            try:
                if iterator is not None and (close := getattr(iterator, "aclose", None)):
                    await close()
            finally:
                if response.background is not None:
                    await response.background()
