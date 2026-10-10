"""Test-only chunked payload capture and Activity request middleware."""

import json
import logging
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)
CHUNK_CHARS = 2000


def log_payload_chunks(
    log: logging.Logger, label: str, body: str, *, capture_id: str | None = None,
) -> str:
    capture_id = capture_id or uuid4().hex
    parts = max(1, (len(body) + CHUNK_CHARS - 1) // CHUNK_CHARS)
    for index in range(parts):
        log.info("%s: %s", label, json.dumps({
            "capture_id": capture_id,
            "part": index + 1,
            "parts": parts,
            "body": body[index * CHUNK_CHARS:(index + 1) * CHUNK_CHARS],
        }, ensure_ascii=True))
    return capture_id


class ActivityPayloadLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "POST" and request.url.path == "/activity/messages":
            # Request.body() caches the bytes for downstream parsing. Do not
            # deserialize the Activity: unknown fields and whitespace matter here.
            body = (await request.body()).decode("utf-8", errors="surrogateescape")
            log_payload_chunks(logger, "Activity request payload", body)
        return await call_next(request)
