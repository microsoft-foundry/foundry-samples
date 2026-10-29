# Copyright (c) Microsoft. All rights reserved.

"""Invoke an HTTP-shaped handler in process, without an HTTP server or client."""

import codecs
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from azure.ai.agentserver.core import get_request_context
from starlette.requests import Request
from starlette.responses import StreamingResponse

InvocationHandler = Callable[[Request], Awaitable[StreamingResponse]]
MAX_FRAME_CHARACTERS = 65_536
MAX_OUTPUT_CHARACTERS = 8_000


def invocation_request(text: str, input_id: str) -> Request:
    """Supply only the current SDK context, not identity from caller JSON."""
    body = json.dumps({"input": text}).encode("utf-8")
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
    """Parse bounded JSON SSE frames, including split UTF-8 and CRLF chunks."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    async for chunk in chunks:
        encoded = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
        # Bound producer chunks before decoding/concatenating them.
        if len(encoded) > MAX_FRAME_CHARACTERS * 4:
            raise ValueError("SSE chunk exceeds its byte budget")
        buffer = (buffer + decoder.decode(encoded)).replace("\r\n", "\n")
        while "\n\n" in buffer:
            frame, _, buffer = buffer.partition("\n\n")
            if len(frame) > MAX_FRAME_CHARACTERS:
                raise ValueError("SSE frame exceeds its character budget")
            data = [
                line[5:].removeprefix(" ") for line in frame.split("\n") if line.startswith("data:")
            ]
            if data:
                event = json.loads("\n".join(data))
                if not isinstance(event, dict):
                    raise ValueError("Expected a JSON SSE object")
                yield event
        if len(buffer) > MAX_FRAME_CHARACTERS:
            raise ValueError("SSE frame exceeds its character budget")
    buffer += decoder.decode(b"", final=True)
    if buffer.strip():
        raise ValueError("SSE ended inside a frame")


class InvocationAdapter:
    """Translate token/done SSE into the existing coordinator's text stream."""

    def __init__(self, handler: InvocationHandler) -> None:
        self._handler = handler

    async def stream(self, text: str, input_id: str) -> AsyncIterator[str]:
        response = await self._handler(invocation_request(text, input_id))
        iterator = None
        try:
            if not 200 <= response.status_code < 300:
                raise ValueError("Invocation failed")
            if not response.headers.get("content-type", "").startswith("text/event-stream"):
                raise ValueError("Expected an SSE response")
            iterator = aiter(response.body_iterator)
            completed = False
            output = ""
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
