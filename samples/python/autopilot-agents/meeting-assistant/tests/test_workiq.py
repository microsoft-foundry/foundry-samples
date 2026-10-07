"""Work IQ tool contracts and real MCP transport; no tenant credentials."""

import base64
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
from mcp import McpError
from mcp.types import CallToolResult, ErrorData, ImageContent, TextContent

from agent.app import MeetingHandlers, on_error
from agent.workiq import (
    MAX_ERROR_DETAILS, MAX_ITEMS, MAX_MCP_RESPONSE_BYTES, MAX_RESPONSE_BYTES,
    WORKIQ_ENDPOINT, WORKIQ_SCOPE, MeetingWorkIQ, WorkIQError,
    WorkIQTransportDiagnostics, bound_response, segment,
)
from agent.request_logging import CHUNK_CHARS
from test_meeting_assistant import SETTINGS, activity

JOIN = "https://teams.microsoft.com/l/meetup-join/synthetic"


def entity(data, status=200):
    return CallToolResult(content=[], structuredContent={
        "results": [{"statusCode": status, "data": data}],
    })


def blob(content=b"WEBVTT\n\n00:00.000 --> 00:01.000\nBudget approved.", **changes):
    return CallToolResult(content=[], structuredContent={
        "statusCode": 200, "contentType": "text/vtt", "sizeBytes": len(content),
        "base64Content": base64.b64encode(content).decode(), **changes,
    })


class WorkIQClientTests(IsolatedAsyncioTestCase):
    def client(self, *responses, log_payloads=False):
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=responses))
        return MeetingWorkIQ(session, log_payloads=log_payloads), session

    async def test_raw_workiq_capture_defaults_off_for_success_and_failure(self):
        for response in (
            entity({"id": "event", "private": "private response"}),
            CallToolResult(content=[TextContent(type="text", text="private error")], isError=True),
            McpError(ErrorData(code=-32603, message="private error")),
        ):
            client, _ = self.client(response)
            with self.assertNoLogs("agent.workiq", level="INFO"):
                if isinstance(response, McpError) or response.isError:
                    with self.assertRaises(WorkIQError):
                        await client.get_event("event")
                else:
                    self.assertEqual((await client.get_event("event"))["id"], "event")

    async def test_raw_workiq_capture_preserves_complete_request_and_result(self):
        response = CallToolResult(content=[
            TextContent(type="text", text="private message\n" + "\U0001f600" * (CHUNK_CHARS * 2)),
        ], structuredContent={"private-field": "private response"}, isError=True)
        client, _ = self.client(response, log_payloads=True)
        with self.assertLogs("agent.workiq", level="INFO") as logs:
            with self.assertRaises(WorkIQError):
                await client.get_event("private-event-id")
        captures = {}
        ids = set()
        for record in logs.records:
            label, encoded = record.getMessage().split(": ", 1)
            entry = json.loads(encoded)
            self.assertLess(len(encoded.encode("utf-8")), 25_000)
            self.assertNotIn("\n", encoded)
            ids.add(entry["capture_id"])
            captures.setdefault(label, []).append(entry)
        self.assertEqual(len(ids), 1)
        restored = {}
        for label, entries in captures.items():
            self.assertEqual([item["part"] for item in entries], list(range(1, len(entries) + 1)))
            self.assertTrue(all(item["parts"] == len(entries) for item in entries))
            restored[label] = json.loads("".join(item["body"] for item in entries))
        self.assertIn("private-event-id", restored["Work IQ request payload"]["arguments"]["entityUrls"][0])
        self.assertEqual(restored["Work IQ response payload"], response.model_dump(mode="json", by_alias=True))
        self.assertGreater(len(captures["Work IQ response payload"]), 1)

    async def test_raw_workiq_capture_includes_successes_and_rpc_error_data(self):
        for response in (
            entity({"id": "event", "private": "private response"}),
            McpError(ErrorData(code=-32603, message="private error", data={"private": "private data"})),
        ):
            client, _ = self.client(response, log_payloads=True)
            with self.assertLogs("agent.workiq", level="INFO") as logs:
                if isinstance(response, McpError):
                    with self.assertRaises(WorkIQError):
                        await client.get_event("event")
                    prefix = "Work IQ RPC error payload: "
                    expected = response.error.model_dump(mode="json", by_alias=True)
                else:
                    self.assertEqual((await client.get_event("event"))["id"], "event")
                    prefix = "Work IQ response payload: "
                    expected = response.model_dump(mode="json", by_alias=True)
            body = "".join(
                json.loads(record.getMessage().removeprefix(prefix))["body"]
                for record in logs.records if record.getMessage().startswith(prefix)
            )
            self.assertEqual(json.loads(body), expected)

    async def test_chat_title_is_a_metadata_fetch(self):
        client, session = self.client(entity({"id": "chat", "topic": " Planning "}))
        self.assertEqual(await client.get_chat_title("chat"), "Planning")
        session.call_tool.assert_awaited_once_with("fetch", {"entityUrls": ["/chats/chat"]})
        for data in ({"id": "chat"}, {"id": "other", "topic": "Planning"}, {"id": "chat", "topic": " "}):
            client, _ = self.client(entity(data))
            with self.assertRaises(ValueError):
                await client.get_chat_title("chat")

    async def test_calendar_filter_and_date_bounds(self):
        client, session = self.client(entity({"value": [
            {"id": "meeting", "isOnlineMeeting": True}, {"id": "appointment"},
        ]}))
        result = await client.list_meetings("2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z")
        self.assertEqual(result, {"items": [{"id": "meeting", "isOnlineMeeting": True}], "has_more": False})
        params = parse_qs(urlsplit(session.call_tool.call_args.args[1]["entityUrls"][0]).query)
        self.assertEqual(params["$top"], [str(MAX_ITEMS)])
        self.assertIn("$select", params)
        for start, end in (
            ("2026-10-01", "2026-10-02"), ("2026-10-02T00:00:00Z", "2026-10-01T00:00:00Z"),
            ("2026-10-01T00:00:00Z", "2026-12-01T00:00:00Z"),
        ):
            with self.assertRaises(ValueError):
                await client.list_meetings(start, end)

    async def test_pagination_is_reported_not_followed(self):
        for next_link in (
            "https://graph.microsoft.com/v1.0/me/events?$skiptoken=next",
            "https://untrusted.invalid/secret",
        ):
            client, session = self.client(entity({"value": [], "@odata.nextLink": next_link}))
            self.assertTrue((await client.list_transcripts("meeting"))["has_more"])
            self.assertEqual(session.call_tool.await_count, 1)
        for data in ({"value": {}}, {"value": [1]}, {"value": [{}] * (MAX_ITEMS + 1)}):
            client, _ = self.client(entity(data))
            with self.assertRaises(WorkIQError):
                await client.list_transcripts("meeting")

    async def test_meeting_binding_and_join_url_validation(self):
        client, session = self.client(entity({"value": [{"id": "m", "chatInfo": {"threadId": "chat"}}]}))
        self.assertEqual((await client.meeting_in_chat(JOIN, "chat"))["id"], "m")
        params = parse_qs(urlsplit(session.call_tool.call_args.args[1]["entityUrls"][0]).query)
        self.assertEqual(params["$filter"], [f"JoinWebUrl eq '{JOIN}'"])
        client, _ = self.client(entity({"value": [{"id": "m", "chatInfo": {"threadId": "other"}}]}))
        with self.assertRaisesRegex(ValueError, "bound"):
            await client.meeting_in_chat(JOIN, "chat")
        client, session = self.client(entity({"value": []}))
        quoted = JOIN + "?context=O'Brien"
        await client.resolve_meeting(quoted)
        params = parse_qs(urlsplit(session.call_tool.call_args.args[1]["entityUrls"][0]).query)
        self.assertEqual(params["$filter"], [f"JoinWebUrl eq '{quoted.replace(chr(39), chr(39) * 2)}'"])
        with self.assertRaises(ValueError):
            await client.resolve_meeting("https://untrusted.invalid/meeting")

    async def test_invitation_uses_actual_occurrence_and_refuses_ambiguity(self):
        current = {
            "id": "current", "isOnlineMeeting": True, "onlineMeeting": {"joinUrl": JOIN},
            "start": {"dateTime": "2026-10-01T09:00:00", "timeZone": "UTC"},
        }
        old = {**current, "id": "old", "start": {"dateTime": "2026-09-30T09:00:00", "timeZone": "UTC"}}
        client, session = self.client(
            entity({"value": [old, current]}),
            entity({"id": "current", "onlineMeeting": {"joinUrl": JOIN}, "body": {"content": "Agenda"}}),
        )
        start = datetime(2026, 10, 1, 9, 10, tzinfo=timezone.utc)
        self.assertEqual((await client.invited_event(JOIN, start))["id"], "current")
        self.assertIn("/me/events/current?", session.call_tool.call_args.args[1]["entityUrls"][0])
        for data in (
            {"value": [current, {**current, "id": "another"}]},
            {"value": [current], "@odata.nextLink": "next"},
            {"value": [{**current, "start": {"dateTime": "2026-10-01T09:00:00", "timeZone": "Eastern Standard Time"}}]},
        ):
            client, _ = self.client(entity(data))
            with self.assertRaises(ValueError):
                await client.invited_event(JOIN, start)

    async def test_transcript_blob(self):
        client, session = self.client(blob())
        self.assertIn("Budget approved", (await client.get_transcript("meeting", "transcript"))["content"])
        session.call_tool.assert_awaited_once_with("fetch_blob", {
            "path": "/me/onlineMeetings/meeting/transcripts/transcript/content?$format=text/vtt",
        })

    async def test_http_errors_retain_safe_inner_code_not_message(self):
        for status in (401, 403, 404, 429, 500):
            client, _ = self.client(entity({"error": {
                "code": "Forbidden", "message": "private error body",
                "innerError": {"code": "GraphAccessToTranscriptsDisabled"},
            }}, status))
            with self.assertRaises(WorkIQError) as caught:
                await client.list_transcripts("meeting")
            self.assertEqual(caught.exception.status, status)
            self.assertEqual(caught.exception.inner_code, "GraphAccessToTranscriptsDisabled")
            self.assertNotIn("private", str(caught.exception))

    async def test_tool_and_protocol_errors_fail_explicitly(self):
        for response in (
            CallToolResult(content=[TextContent(type="text", text="private")], isError=True),
            McpError(ErrorData(code=-32603, message="private")),
            CallToolResult(content=[], structuredContent={"results": []}),
            CallToolResult(content=[], structuredContent={"results": [{"data": {}}]}),
            CallToolResult(content=[TextContent(type="text", text="not json")]),
        ):
            client, _ = self.client(response)
            with self.assertRaises(WorkIQError) as caught:
                await client.get_event("event")
            self.assertNotIn("private", str(caught.exception))
        client, _ = self.client(CallToolResult(content=[TextContent(
            type="text", text=json.dumps({"results": [{"statusCode": 200, "data": {"id": "event"}}]}),
        )]))
        self.assertEqual((await client.get_event("event"))["id"], "event")

    async def test_error_flag_does_not_hide_structured_status(self):
        result = entity({"error": {
            "code": "Forbidden", "innerError": {"code": "GraphAccessToTranscriptsDisabled"},
        }}, 403)
        result.isError = True
        client, _ = self.client(result)
        with self.assertRaises(WorkIQError) as caught:
            await client.list_transcripts("meeting")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.inner_code, "GraphAccessToTranscriptsDisabled")

    async def test_live_workiq_error_envelope_retains_status_code_and_request_id(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        data = {"requestId": request_id, "results": [{
            "data": None, "statusCode": 400, "error": {"error": {
                "code": "BadRequest", "message": "private response details",
                "innerError": {"request-id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            }},
        }]}
        for structured in (True, False):
            for flagged in (True, False):
                with self.subTest(structured=structured, flagged=flagged):
                    response = CallToolResult(
                        structuredContent=data if structured else None,
                        content=[] if structured else [
                            TextContent(type="text", text=json.dumps(data)),
                        ],
                        isError=flagged,
                    )
                    client, _ = self.client(response)
                    with self.assertRaises(WorkIQError) as caught:
                        await client.resolve_meeting(JOIN)
                    self.assertEqual(caught.exception.status, 400)
                    self.assertEqual(caught.exception.code, "BadRequest")
                    self.assertEqual(caught.exception.request_id, request_id)
                    self.assertNotIn("private", str(caught.exception))

    async def test_blob_error_text_is_parsed_but_never_used_as_transcript(self):
        data = {"statusCode": 403, "error": {"code": "Forbidden"}}
        client, _ = self.client(CallToolResult(
            content=[TextContent(type="text", text=json.dumps(data))], isError=True,
        ))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_transcript("meeting", "transcript")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.code, "Forbidden")

    async def test_error_flag_with_success_status_never_becomes_success(self):
        response = entity({"id": "event"})
        response.isError = True
        client, _ = self.client(response)
        with self.assertRaisesRegex(WorkIQError, "ToolErrorSuccessStatus"):
            await client.get_event("event")

    async def test_direct_error_codes_survive_without_an_http_status(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        for data in (
            {"code": "Forbidden", "requestId": request_id},
            {"error": {"code": "Forbidden", "innerError": {"request-id": request_id}}},
            {"error": {"error": {"code": "Forbidden"}, "innerError": {"request-id": request_id}}},
        ):
            for structured in (True, False):
                with self.subTest(data=data, structured=structured):
                    client, _ = self.client(CallToolResult(
                        structuredContent=data if structured else None,
                        content=[] if structured else [
                            TextContent(type="text", text=json.dumps(data)),
                        ], isError=True,
                    ))
                    with self.assertRaises(WorkIQError) as caught:
                        await client.get_event("event")
                    error = caught.exception
                    self.assertEqual(error.status, 0)
                    self.assertEqual(error.code, "Forbidden")
                    self.assertEqual(error.request_id, request_id)
                    self.assertEqual(error.diagnostics.kind, "error_code_without_failure_status")

    async def test_opaque_tool_errors_have_distinct_safe_shapes(self):
        cases = (
            ([TextContent(type="text", text="private response")], None, "ToolErrorNonJsonText"),
            ([TextContent(type="text", text=json.dumps(["private"]))], None, "ToolErrorNonObjectJson"),
            ([], {"private-key": "private response"}, "ToolErrorUnknownEnvelope"),
            ([], None, "ToolErrorMissingText"),
            ([ImageContent(type="image", data="cHJpdmF0ZQ==", mimeType="image/png")],
             None, "ToolErrorNonTextContent"),
        )
        for content, data, code in cases:
            with self.subTest(code=code):
                client, _ = self.client(CallToolResult(
                    content=content, structuredContent=data, isError=True,
                ))
                with self.assertRaises(WorkIQError) as caught:
                    await client.get_event("event")
                error = caught.exception
                self.assertEqual(error.code, code)
                self.assertEqual(error.diagnostics.tool, "fetch")
                with self.assertLogs("agent.app", level="ERROR") as logs:
                    await on_error(SimpleNamespace(), error)
                output = "\n".join(logs.output)
                self.assertIn(code, output)
                self.assertIn(error.diagnostics.kind, output)
                self.assertNotIn("private", output)
                self.assertNotIn("cHJpdmF0ZQ", output)

    async def test_multiple_error_blocks_preserve_all_safe_failures(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        client, _ = self.client(CallToolResult(content=[
            TextContent(type="text", text="private unstructured message"),
            TextContent(type="text", text=json.dumps({
                "error": {"code": "Forbidden", "message": "private response"},
                "requestId": request_id,
            })),
            TextContent(type="text", text=json.dumps({
                "results": [
                    {"statusCode": 403, "error": {"code": "AccessDenied"}},
                    {"statusCode": 429, "error": {"code": "TooManyRequests"}},
                ],
            })),
        ], isError=True))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_event("event")
        error = caught.exception
        self.assertEqual(error.status, 403)
        self.assertEqual(error.code, "AccessDenied")
        self.assertEqual(error.diagnostics.content_counts, (("text", 3),))
        self.assertEqual(error.diagnostics.json_types, ("non_json", "object", "object"))
        fields = json.dumps(error.diagnostic_fields())
        for code in ("Forbidden", "AccessDenied", "TooManyRequests", request_id):
            self.assertIn(code, fields)
        self.assertNotIn("private", fields)

    async def test_rpc_error_preserves_protocol_code_and_safe_error_data(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        client, _ = self.client(McpError(ErrorData(
            code=-32601, message="private protocol message",
            data={"statusCode": 403, "error": {
                "code": "Forbidden", "message": "private response",
                "innerError": {"request-id": request_id},
            }},
        )))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_event("event")
        error = caught.exception
        self.assertEqual(error.status, 403)
        self.assertEqual(error.code, "Forbidden")
        self.assertEqual(error.request_id, request_id)
        self.assertEqual(error.diagnostics.rpc_code, -32601)
        with self.assertLogs("agent.app", level="ERROR") as logs:
            await on_error(SimpleNamespace(), error)
        output = "\n".join(logs.output)
        self.assertIn("-32601", output)
        self.assertIn("rpc_error", output)
        self.assertNotIn("private", output)

    async def test_plain_text_retains_labeled_uuid_and_aadsts_code_only(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        text = (
            f"private details at https://private.invalid/path. "
            f"AADSTS65001: private message. RequestId: {request_id}"
        )
        for response in (
            CallToolResult(content=[TextContent(type="text", text=text)], isError=True),
            CallToolResult(content=[TextContent(type="text", text=json.dumps(text))], isError=True),
            McpError(ErrorData(code=-32000, message=text, data={})),
        ):
            client, _ = self.client(response)
            with self.assertRaises(WorkIQError) as caught:
                await client.get_event("event")
            error = caught.exception
            self.assertEqual(error.code, "AADSTS65001")
            self.assertEqual(error.request_id, request_id)
            self.assertNotIn("private", json.dumps(error.diagnostic_fields()))

    async def test_mcp_metadata_correlation_is_retained_without_error_content(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        client, _ = self.client(CallToolResult(
            content=[], isError=True,
            _meta={"requestId": request_id, "private": "private response"},
        ))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_event("event")
        self.assertEqual(caught.exception.request_id, request_id)
        self.assertEqual(caught.exception.diagnostics.meta_request_id, request_id)
        self.assertNotIn("private", json.dumps(caught.exception.diagnostic_fields()))

    async def test_error_diagnostics_are_bounded_and_report_truncation(self):
        client, _ = self.client(CallToolResult(content=[], structuredContent={
            "errors": [{"code": f"Failure{number}"} for number in range(MAX_ERROR_DETAILS + 1)],
        }, isError=True))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_event("event")
        self.assertEqual(len(caught.exception.diagnostics.failures), MAX_ERROR_DETAILS)
        self.assertTrue(caught.exception.diagnostics.truncated)
        client, _ = self.client(CallToolResult(content=[
            TextContent(type="text", text="x" * (MAX_RESPONSE_BYTES + 1)),
        ], isError=True))
        with self.assertRaisesRegex(WorkIQError, "ResponseTooLarge") as caught:
            await client.get_event("event")
        self.assertEqual(caught.exception.diagnostics.kind, "oversized_error_text")

    async def test_deep_error_json_is_a_safe_explicit_failure(self):
        client, _ = self.client(CallToolResult(content=[
            TextContent(type="text", text="[" * 2000 + '"private"' + "]" * 2000),
        ], isError=True))
        with patch("agent.workiq.json.loads", side_effect=RecursionError):
            with self.assertRaisesRegex(WorkIQError, "ToolErrorJsonDepth") as caught:
                await client.get_event("event")
        self.assertNotIn("private", json.dumps(caught.exception.diagnostic_fields()))

    async def test_invalid_request_id_and_error_codes_are_not_retained(self):
        client, _ = self.client(CallToolResult(content=[], structuredContent={
            "requestId": "private context", "results": [{
                "statusCode": 403, "error": {"error": {
                    "code": "private error message", "innerError": {
                        "code": "private error message", "request-id": "private context",
                    },
                }},
            }],
        }))
        with self.assertRaises(WorkIQError) as caught:
            await client.get_event("event")
        self.assertEqual(caught.exception.code, "RequestFailed")
        self.assertIsNone(caught.exception.inner_code)
        self.assertIsNone(caught.exception.request_id)

    async def test_invalid_or_oversized_blobs_fail_without_synthesis(self):
        for result in (
            blob(sizeBytes=MAX_RESPONSE_BYTES + 1), blob(base64Content="!!!!"),
            blob(sizeBytes=0), blob(contentType="text/html"), blob(content=b"\xff"),
            CallToolResult(content=[TextContent(type="text", text="WEBVTT")]),
        ):
            client, _ = self.client(result)
            with self.assertRaises(WorkIQError):
                await client.get_transcript("meeting", "transcript")
        client, _ = self.client(entity({"body": "x" * (MAX_RESPONSE_BYTES + 1)}))
        with self.assertRaisesRegex(WorkIQError, "ResponseTooLarge"):
            await client.get_event("event")

    async def test_relative_paths_only(self):
        client, session = self.client()
        for path in ("https://graph.microsoft.com/v1.0/me/events", "//untrusted.invalid/events", "/me/events?x=1"):
            with self.assertRaises(ValueError):
                await client._get(path)
        session.call_tool.assert_not_awaited()


class MCPTransportTests(IsolatedAsyncioTestCase):
    async def test_real_mcp_errors_use_current_tool_response_header_not_stale_ids(self):
        request_id = "11111111-2222-3333-4444-555555555555"
        init_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        calls = 0

        def handle(request):
            nonlocal calls
            message = json.loads(request.content)
            headers = {"x-ms-request-id": init_id}
            if message["method"] == "notifications/initialized":
                return httpx.Response(202, headers=headers)
            if message["method"] == "initialize":
                result = {
                    "protocolVersion": message["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "synthetic-workiq", "version": "1"},
                }
            elif message["method"] == "tools/list":
                result = {"tools": [{"name": "fetch", "inputSchema": {"type": "object"}}]}
            else:
                self.assertEqual(message["method"], "tools/call")
                calls += 1
                headers = {"x-ms-request-id": request_id if calls == 1 else "private-invalid-id"}
                result = CallToolResult(content=[
                    TextContent(type="text", text="private tool error"),
                ], isError=True).model_dump(by_alias=True)
            return httpx.Response(200, headers=headers, json={
                "jsonrpc": "2.0", "id": message["id"], "result": result,
            })

        original_client = httpx.AsyncClient
        auth = SimpleNamespace(exchange_token=AsyncMock(return_value=SimpleNamespace(token="synthetic-token")))
        handlers = MeetingHandlers(
            SimpleNamespace(auth=auth), replace(SETTINGS, log_workiq_payloads=True),
        )
        with (
            patch("agent.app.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(
                transport=httpx.MockTransport(handle), **kwargs,
            )),
            self.assertLogs("agent.workiq", level="INFO") as logs,
        ):
            async with handlers.workiq_client(SimpleNamespace(activity=activity())) as client:
                for expected in (request_id, None):
                    with self.assertRaises(WorkIQError) as caught:
                        await client.get_chat_title("chat")
                    error = caught.exception
                    self.assertEqual(error.code, "ToolErrorNonJsonText")
                    self.assertEqual(error.request_id, expected)
                    self.assertEqual(error.diagnostics.transport_request_id, expected)
                    self.assertNotIn(init_id, json.dumps(error.diagnostic_fields()))
                    self.assertNotIn("private", json.dumps(error.diagnostic_fields()))
        output = "\n".join(logs.output)
        self.assertIn("private tool error", output)
        self.assertNotIn("synthetic-token", output)

    async def test_http_error_payload_capture_is_opt_in_and_keeps_body_readable(self):
        async def handle(request):
            return httpx.Response(403, content=b"private HTTP error\xff")

        for enabled in (False, True):
            diagnostics = WorkIQTransportDiagnostics(log_payloads=enabled)
            capture = (
                self.assertLogs("agent.workiq", level="INFO") if enabled
                else self.assertNoLogs("agent.workiq", level="INFO")
            )
            with capture as logs:
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handle),
                    event_hooks={"response": [diagnostics.on_response]},
                ) as client:
                    response = await client.get(WORKIQ_ENDPOINT)
                    self.assertEqual(response.content, b"private HTTP error\xff")
            if enabled:
                entry = json.loads(logs.records[0].getMessage().removeprefix("Work IQ HTTP error payload: "))
                payload = json.loads(entry["body"])
                self.assertEqual(payload["statusCode"], 403)
                self.assertEqual(
                    payload["body"].encode("utf-8", errors="surrogateescape"), response.content,
                )

    async def test_handler_uses_real_initialized_mcp_transport_with_agent_user_token(self):
        requests = []

        def handle(request):
            requests.append(request)
            self.assertEqual(str(request.url), WORKIQ_ENDPOINT)
            self.assertEqual(request.headers["Accept-Encoding"], "identity")
            self.assertEqual(request.headers["Authorization"], "Bearer synthetic-token")
            message = json.loads(request.content)
            if message["method"] == "notifications/initialized":
                return httpx.Response(202)
            if message["method"] == "initialize":
                result = {
                    "protocolVersion": message["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "synthetic-workiq", "version": "1"},
                }
            elif message["method"] == "tools/list":
                result = {"tools": [
                    {"name": name, "inputSchema": {"type": "object"}}
                    for name in ("fetch", "fetch_blob")
                ]}
            else:
                self.assertEqual(message["method"], "tools/call")
                if message["params"]["name"] == "fetch":
                    self.assertEqual(message["params"]["arguments"], {"entityUrls": ["/chats/chat"]})
                    result = entity({"id": "chat", "topic": "Planning"}).model_dump(by_alias=True)
                else:
                    self.assertEqual(message["params"]["name"], "fetch_blob")
                    self.assertEqual(message["params"]["arguments"], {
                        "path": "/me/onlineMeetings/meeting/transcripts/transcript/content?$format=text/vtt",
                    })
                    result = blob().model_dump(by_alias=True)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})

        original_client = httpx.AsyncClient
        def client_factory(**kwargs):
            return original_client(transport=httpx.MockTransport(handle), **kwargs)

        auth = SimpleNamespace(exchange_token=AsyncMock(return_value=SimpleNamespace(token="synthetic-token")))
        handlers = MeetingHandlers(SimpleNamespace(auth=auth), SETTINGS)
        context = SimpleNamespace(activity=activity())
        with patch("agent.app.httpx.AsyncClient", side_effect=client_factory):
            async with handlers.workiq_client(context) as client:
                self.assertEqual(await client.get_chat_title("chat"), "Planning")
                self.assertIn("Budget approved", (await client.get_transcript("meeting", "transcript"))["content"])
        auth.exchange_token.assert_awaited_once_with(
            context, scopes=[WORKIQ_SCOPE], auth_handler_id="AGENTIC",
        )
        self.assertGreaterEqual(len(requests), 3)

    async def test_transport_response_bound_and_redirect_rejection(self):
        class LargeStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"x" * (MAX_MCP_RESPONSE_BYTES + 1)
        async def handle(request):
            return httpx.Response(200, stream=LargeStream())
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), event_hooks={"response": [bound_response]},
        ) as client:
            with self.assertRaisesRegex(WorkIQError, "ResponseTooLarge"):
                await client.get(WORKIQ_ENDPOINT)
        with self.assertRaisesRegex(WorkIQError, "RedirectRejected"):
            await bound_response(httpx.Response(302))
        with self.assertRaisesRegex(WorkIQError, "UnsupportedContentEncoding"):
            await bound_response(httpx.Response(200, headers={"Content-Encoding": "gzip"}))


class PathTests(TestCase):
    def test_opaque_identifiers_are_encoded_and_bounded(self):
        self.assertEqual(segment("a/b?c#d"), "a%2Fb%3Fc%23d")
        for value in ("", ".", "..", "x" * 4097):
            with self.assertRaises(ValueError):
                segment(value)
