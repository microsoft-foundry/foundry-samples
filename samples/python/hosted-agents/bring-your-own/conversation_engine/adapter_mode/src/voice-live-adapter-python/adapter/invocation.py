# Copyright (c) Microsoft. All rights reserved.

"""Invoke an HTTP-shaped handler in process, without an HTTP server or client."""

import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from azure.ai.agentserver.core import get_request_context
from starlette.requests import Request
from starlette.responses import StreamingResponse

InvocationHandler = Callable[[Request], Awaitable[StreamingResponse]]
MAX_FRAME_BYTES = 512 * 1024
MAX_OUTPUT_CHARACTERS = 8_000
MAX_DATA_BYTES = 65_536


def invocation_request(text: str | Mapping[str, Any], input_id: str) -> Request:
    """Supply only the current SDK context, not identity from caller JSON."""
    # InputDataPart deeply freezes objects; thaw mappings only for JSON encoding.
    body = json.dumps({"input": text}, default=dict, ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )
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
    """Parse bounded UTF-8 event lines, independent of producer write boundaries."""
    line = bytearray()
    data: list[str] = []
    frame_bytes = 0
    first_line = True
    skip_lf = False

    def finish_line() -> dict[str, Any] | None:
        nonlocal first_line, frame_bytes
        text = line.decode("utf-8")
        line.clear()
        if first_line:
            first_line = False
            if text.startswith("\ufeff"):
                text = text[1:]
                frame_bytes -= 3
        if frame_bytes > MAX_FRAME_BYTES:
            raise ValueError("SSE frame exceeds its byte budget")
        if not text:
            frame_bytes = 0
            if data:
                payload = "\n".join(data)
                data.clear()
                event = json.loads(payload, parse_constant=_reject_json_constant)
                if not isinstance(event, dict):
                    raise ValueError("Expected a JSON SSE object")
                return event
        else:
            field, _, value = text.partition(":")
            if field == "data":
                data.append(value.removeprefix(" "))
        return None

    async for chunk in chunks:
        if not isinstance(chunk, (str, bytes, bytearray, memoryview)):
            raise ValueError("Expected a text or bytes SSE chunk")
        # Slice before encoding/copying. Even empty/comment-only ready streams yield control.
        for offset in range(0, max(1, len(chunk)), 1024):
            piece = chunk[offset:offset + 1024]
            encoded = piece.encode("utf-8") if isinstance(piece, str) else bytes(piece)
            for value in encoded:
                if skip_lf:
                    skip_lf = False
                    if value == 10:
                        continue
                frame_bytes += 1
                # Count CRLF as LF, and allow the first line's optional three-byte BOM.
                if frame_bytes > MAX_FRAME_BYTES + (3 if first_line else 0):
                    raise ValueError("SSE frame exceeds its byte budget")
                if value in (10, 13):
                    event = finish_line()
                    skip_lf = value == 13
                    if event is not None:
                        yield event
                else:
                    line.append(value)
            await asyncio.sleep(0)
    if line:
        finish_line()  # A trailing comment is harmless; EOF never dispatches pending data.
    if data:
        raise ValueError("SSE ended inside an event")


def _reject_json_constant(_value: str) -> None:
    raise ValueError("Expected finite JSON numbers")


class InvocationAdapter:
    """Translate token/data/done SSE into ordered text and JSON output."""

    def __init__(self, handler: InvocationHandler) -> None:
        self._handler = handler

    async def stream(
        self, text: str | Mapping[str, Any], input_id: str
    ) -> AsyncIterator[str | dict[str, Any]]:
        response = await self._handler(invocation_request(text, input_id))
        iterator = response.body_iterator
        try:
            iterator = aiter(iterator)
            if not 200 <= response.status_code < 300:
                raise ValueError("Invocation failed")
            media_type = response.headers.get("content-type", "").partition(";")[0].strip()
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
                        json.dumps(data, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":")).encode("utf-8")
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
            primary_error = sys.exception()
            cleanup_error = None
            # Attempt both steps independently; preserve the primary iteration/send failure.
            for close in (getattr(iterator, "aclose", None), response.background):
                if close is not None:
                    try:
                        await close()
                    except (Exception, asyncio.CancelledError) as error:
                        cleanup_error = cleanup_error or error
                        logging.getLogger("voice_live_bridge").warning(
                            "Handler cleanup failed; error_type=%s", type(error).__name__,
                        )
            if cleanup_error is not None and (
                primary_error is None or isinstance(primary_error, GeneratorExit)
            ):
                raise cleanup_error
