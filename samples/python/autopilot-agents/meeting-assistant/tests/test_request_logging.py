"""Raw request capture must preserve the body and the downstream response."""

import json
from unittest import IsolatedAsyncioTestCase

import httpx
from azure.ai.agentserver.activity import ActivityAgentServerHost
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import Response
from starlette.routing import Route

from agent.request_logging import ActivityPayloadLoggingMiddleware, CHUNK_CHARS

LOG_NAME = "agent.request_logging"
PREFIX = "Activity request payload: "


class RequestLoggingTests(IsolatedAsyncioTestCase):
    async def capture(self, body, status=200):
        async def endpoint(request):
            self.assertTrue(logs.records, "Capture must precede downstream request handling.")
            self.assertEqual(await request.body(), body)
            return Response(body, status_code=status, headers={"x-test": "preserved"})

        app = Starlette(
            routes=[Route("/activity/messages", endpoint, methods=["POST"])],
            middleware=[Middleware(ActivityPayloadLoggingMiddleware)],
        )
        with self.assertLogs(LOG_NAME, level="INFO") as logs:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as client:
                response = await client.post(
                    "/activity/messages", content=body,
                    headers={"Authorization": "Bearer synthetic-header-secret", "Content-Type": "application/json"},
                )
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.content, body)
        self.assertEqual(response.headers["x-test"], "preserved")
        self.assertNotIn("synthetic-header-secret", "\n".join(logs.output))
        entries = [json.loads(record.getMessage().removeprefix(PREFIX)) for record in logs.records]
        self.assertEqual(len({entry["capture_id"] for entry in entries}), 1)
        self.assertEqual([entry["part"] for entry in entries], list(range(1, len(entries) + 1)))
        self.assertTrue(all(entry["parts"] == len(entries) for entry in entries))
        restored = "".join(entry["body"] for entry in entries).encode("utf-8", errors="surrogateescape")
        self.assertEqual(restored, body)
        return entries

    async def test_all_activity_types_including_unknown_fields_are_captured(self):
        for kind in ("event", "message", "invoke", "conversationUpdate", "unknown"):
            with self.subTest(kind=kind):
                body = (
                    '{\r\n  "type": "' + kind + '", "unknown": {"text": "caf\u00e9"}, '
                    '"value": {"unrecognized": true}\r\n}'
                ).encode("utf-8")
                await self.capture(body)

    async def test_rejected_and_malformed_requests_are_still_captured(self):
        for body, status in ((b'{"type":"event"}', 401), (b"not-json\xff", 400), (b"", 400)):
            with self.subTest(status=status, body=body):
                await self.capture(body, status)

    async def test_large_unicode_body_is_losslessly_chunked_without_log_newlines(self):
        body = json.dumps({"text": "\U0001f600\n" * CHUNK_CHARS}, ensure_ascii=False).encode("utf-8")
        entries = await self.capture(body)
        self.assertGreater(len(entries), 1)
        for entry in entries:
            encoded = json.dumps(entry, ensure_ascii=True)
            self.assertLess(len(encoded.encode("utf-8")), 25_000)
            self.assertNotIn("\n", encoded)

    async def test_other_endpoints_and_methods_are_not_captured(self):
        async def endpoint(request):
            return Response(await request.body())

        app = Starlette(
            routes=[
                Route("/readiness", endpoint, methods=["GET"]),
                Route("/other", endpoint, methods=["POST"]),
                Route("/activity/messages", endpoint, methods=["GET"]),
            ],
            middleware=[Middleware(ActivityPayloadLoggingMiddleware)],
        )
        with self.assertNoLogs(LOG_NAME):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as client:
                await client.get("/readiness")
                await client.post("/other", content=b"not an Activity request")
                await client.get("/activity/messages")

    async def test_installed_activity_host_captures_even_when_ingress_rejects_body(self):
        async def endpoint(request):
            return Response(status_code=401)

        host = ActivityAgentServerHost(request_handler=endpoint, configure_observability=None)
        host.add_middleware(ActivityPayloadLoggingMiddleware)
        body = b'{"type":"event","name":"application/vnd.microsoft.meetingStart","extra":true}'
        with self.assertLogs(LOG_NAME, level="INFO") as logs:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(host), base_url="https://test") as client:
                response = await client.post("/activity/messages", content=body)
        self.assertGreaterEqual(response.status_code, 400)
        entry = json.loads(logs.records[0].getMessage().removeprefix(PREFIX))
        self.assertEqual(entry["body"].encode("utf-8"), body)
