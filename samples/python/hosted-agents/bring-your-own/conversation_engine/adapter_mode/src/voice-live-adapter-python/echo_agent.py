# Copyright (c) Microsoft. All rights reserved.

"""A plain HTTP-shaped Echo handler. It knows nothing about Voice or Bridge."""

import asyncio
import json
import re
from collections.abc import AsyncIterator

from starlette.requests import Request
from starlette.responses import StreamingResponse


async def handle_invocation(request: Request) -> StreamingResponse:
    """Echo text as token/done SSE, or a JSON object as data/done SSE."""
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), (str, dict)):
        raise ValueError("Expected an input string or JSON object")
    text = payload["input"]

    async def stream() -> AsyncIterator[str]:
        if isinstance(text, dict):
            yield (
                "data: "
                + json.dumps({"type": "data", "data": text}, ensure_ascii=False)
                + "\n\n"
            )
            yield 'data: {"type":"done","full_text":""}\n\n'
            return
        for match in re.finditer(r"\s*\S+|\s+$", text):
            await asyncio.sleep(0)
            yield (
                "data: "
                + json.dumps({"type": "token", "content": match[0]}, ensure_ascii=False)
                + "\n\n"
            )
        yield (
            "data: " + json.dumps({"type": "done", "full_text": text}, ensure_ascii=False) + "\n\n"
        )

    return StreamingResponse(stream(), media_type="text/event-stream")
