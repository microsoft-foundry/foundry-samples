"""Bounded, deterministic meeting reads through the Work IQ MCP server."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn
from urllib.parse import quote, urlencode, urlsplit

import httpx
from mcp import ClientSession, McpError
from mcp.types import CallToolResult, TextContent

from .request_logging import log_payload_chunks

logger = logging.getLogger(__name__)

WORKIQ_ENDPOINT = "https://workiq.svc.cloud.microsoft/mcp"
WORKIQ_SCOPE = "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask"
MAX_RESPONSE_BYTES = 2_000_000
MAX_MCP_RESPONSE_BYTES = 4_000_000
MAX_ITEMS = 100
MAX_ERROR_DETAILS = 16


@dataclass(frozen=True)
class WorkIQFailure:
    status: int = 0
    code: str | None = None
    inner_code: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class WorkIQDiagnostics:
    tool: str
    kind: str
    structured_type: str = "absent"
    content_counts: tuple[tuple[str, int], ...] = ()
    text_bytes: int = 0
    json_types: tuple[str, ...] = ()
    rpc_code: int | None = None
    transport_request_id: str | None = None
    meta_request_id: str | None = None
    failures: tuple[WorkIQFailure, ...] = ()
    truncated: bool = False


class WorkIQError(Exception):
    """An actionable failure without response bodies, paths, or access tokens."""

    def __init__(
        self, status: int, code: str, inner_code: str | None = None,
        *, request_id: str | None = None, diagnostics: WorkIQDiagnostics | None = None,
    ):
        self.status = status
        self.code = code
        self.inner_code = inner_code
        self.request_id = correlation_id(request_id)
        self.diagnostics = diagnostics
        super().__init__(f"Work IQ returned {status} ({code}).")

    def diagnostic_fields(self) -> dict[str, Any]:
        return asdict(self.diagnostics) if self.diagnostics is not None else {}


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_MCP_RESPONSE_BYTES:
                raise WorkIQError(0, "ResponseTooLarge")
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


async def bound_response(response: httpx.Response) -> None:
    if response.is_redirect:
        raise WorkIQError(response.status_code, "RedirectRejected")
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise WorkIQError(response.status_code, "UnsupportedContentEncoding")
    response.stream = LimitedStream(response.stream)


def error_code(value: object, default: str | None = None) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[\w.-]{1,100}", value):
        return value
    return default


def correlation_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(
        r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", value,
    ):
        return value
    return None


def json_type(value: object) -> str:
    return {
        dict: "object", list: "array", str: "string", int: "integer",
        float: "number", bool: "boolean", type(None): "null",
    }.get(type(value), "other")


def request_id_from(data: dict[str, Any]) -> str | None:
    return next((
        valid for key in ("requestId", "request-id", "request_id", "correlationId")
        if (valid := correlation_id(data.get(key))) is not None
    ), None)


class WorkIQTransportDiagnostics:
    """Correlate the sequential tool calls made by one turn's MCP client."""

    def __init__(self, *, log_payloads: bool = False) -> None:
        self.request_id: str | None = None
        self.capture_id: str | None = None
        self.log_payloads = log_payloads

    async def on_response(self, response: httpx.Response) -> None:
        if response.request.method == "POST":
            request = json.loads(response.request.content)
            if isinstance(request, dict) and request.get("method") == "tools/call":
                self.request_id = next((
                    valid for name in (
                        "request-id", "x-request-id", "x-ms-request-id",
                        "x-ms-correlation-request-id",
                    )
                    if (valid := correlation_id(response.headers.get(name))) is not None
                ), None)
        await bound_response(response)
        if self.log_payloads and response.is_error:
            body = (await response.aread()).decode("utf-8", errors="surrogateescape")
            log_payload_chunks(logger, "Work IQ HTTP error payload", json.dumps({
                "statusCode": response.status_code, "body": body,
            }), capture_id=self.capture_id)


def failure_details(data: dict[str, Any], request_id: str | None = None) -> WorkIQFailure:
    request_id = request_id or request_id_from(data)
    error = data.get("error")
    if not isinstance(error, dict):
        body = data.get("data")
        error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        error = data
    status = data.get("statusCode")
    for _ in range(MAX_ERROR_DETAILS):
        inner = error.get("innerError")
        request_id = request_id or request_id_from(error) or (
            request_id_from(inner) if isinstance(inner, dict) else None
        )
        if status is None:
            status = error.get("statusCode")
        nested = error.get("error")
        if not isinstance(nested, dict):
            break
        error = nested
    inner = error.get("innerError")
    return WorkIQFailure(
        status if type(status) is int and 100 <= status <= 599 else 0,
        error_code(error.get("code")),
        error_code(inner.get("code")) if isinstance(inner, dict) else None,
        request_id or (request_id_from(inner) if isinstance(inner, dict) else None),
    )


def text_failure_details(text: str) -> WorkIQFailure:
    # Extract only labeled UUIDs and the fixed AADSTS numeric code format.
    request = re.search(
        r"\b(?:request[-_ ]?id|correlation[-_ ]?id)[\"']?\s*[:=]\s*[\"']?"
        r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\b",
        text, re.IGNORECASE,
    )
    code = re.search(r"\bAADSTS[0-9]{5,10}\b", text)
    return WorkIQFailure(
        code=code.group(0) if code else None,
        request_id=correlation_id(request.group(1)) if request else None,
    )


def segment(value: str) -> str:
    if not value.strip() or value in {".", ".."} or len(value) > 4096:
        raise ValueError("A nonempty resource identifier of at most 4096 characters is required.")
    return quote(value, safe="")


class MeetingWorkIQ:
    def __init__(
        self, session: ClientSession,
        *, transport_diagnostics: WorkIQTransportDiagnostics | None = None,
        log_payloads: bool = False,
    ):
        self.session = session
        self._transport_diagnostics = transport_diagnostics
        self._log_payloads = log_payloads

    async def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        capture_id = None
        if self._log_payloads:
            capture_id = log_payload_chunks(logger, "Work IQ request payload", json.dumps({
                "tool": tool, "arguments": arguments,
            }, ensure_ascii=False))
        if self._transport_diagnostics is not None:
            self._transport_diagnostics.request_id = None
            self._transport_diagnostics.capture_id = capture_id
        try:
            result = await self.session.call_tool(tool, arguments)
        except McpError as error:
            if self._log_payloads:
                log_payload_chunks(
                    logger, "Work IQ RPC error payload",
                    error.error.model_dump_json(by_alias=True), capture_id=capture_id,
                )
            text = error.error.message
            text_bytes = len(text.encode("utf-8"))
            text_details = (
                text_failure_details(text)
                if text_bytes <= MAX_RESPONSE_BYTES else WorkIQFailure()
            )
            details = text_details
            if isinstance(error.error.data, dict):
                details = failure_details(error.error.data, text_details.request_id)
                details = replace(details, code=details.code or text_details.code)
            transport_id = (
                self._transport_diagnostics.request_id
                if self._transport_diagnostics is not None else None
            )
            raise WorkIQError(
                details.status, details.code or "MCPRequestFailed", details.inner_code,
                request_id=details.request_id or transport_id,
                diagnostics=WorkIQDiagnostics(
                    error_code(tool) or "unknown", "rpc_error",
                    structured_type=json_type(error.error.data),
                    text_bytes=text_bytes, rpc_code=error.error.code,
                    transport_request_id=transport_id,
                    failures=tuple(dict.fromkeys((details, text_details))),
                    truncated=text_bytes > MAX_RESPONSE_BYTES,
                ),
            ) from None
        if self._log_payloads:
            log_payload_chunks(
                logger, "Work IQ response payload",
                result.model_dump_json(by_alias=True), capture_id=capture_id,
            )
        data = result.structuredContent
        if result.isError:
            self._raise_tool_error(
                tool, result,
                self._transport_diagnostics.request_id
                if self._transport_diagnostics is not None else None,
            )
        if data is None and tool == "fetch":
            text = [item.text for item in result.content if isinstance(item, TextContent)]
            if len(text) != 1 or len(text[0].encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise WorkIQError(0, "InvalidResponse")
            try:
                data = json.loads(text[0])
            except ValueError:
                raise WorkIQError(0, "InvalidJson") from None
        if not isinstance(data, dict):
            raise WorkIQError(0, "InvalidResponse")
        if len(json.dumps(data).encode("utf-8")) > MAX_MCP_RESPONSE_BYTES:
            raise WorkIQError(0, "ResponseTooLarge")
        return data

    @staticmethod
    def _raise_tool_error(
        tool: str, result: CallToolResult, transport_id: str | None,
    ) -> NoReturn:
        texts = [item.text for item in result.content if isinstance(item, TextContent)]
        counts = Counter(
            item.type if item.type in {"text", "image", "audio", "resource", "resource_link"}
            else "other" for item in result.content
        )
        diagnostics = WorkIQDiagnostics(
            error_code(tool) or "unknown", "tool_error",
            structured_type=(
                json_type(result.structuredContent)
                if result.structuredContent is not None else "absent"
            ),
            content_counts=tuple(sorted(counts.items())),
            text_bytes=sum(len(text.encode("utf-8")) for text in texts),
            transport_request_id=transport_id,
            meta_request_id=request_id_from(result.meta) if isinstance(result.meta, dict) else None,
            truncated=len(texts) > MAX_ERROR_DETAILS,
        )
        if diagnostics.text_bytes > MAX_RESPONSE_BYTES:
            raise WorkIQError(
                0, "ResponseTooLarge", diagnostics=replace(diagnostics, kind="oversized_error_text"),
            )
        objects: list[dict[str, Any]] = []
        if result.structuredContent is not None:
            try:
                size = len(json.dumps(result.structuredContent).encode("utf-8"))
            except RecursionError:
                raise WorkIQError(
                    0, "ToolErrorJsonDepth",
                    diagnostics=replace(diagnostics, kind="error_json_depth_exceeded"),
                ) from None
            if size > MAX_MCP_RESPONSE_BYTES:
                raise WorkIQError(
                    0, "ResponseTooLarge",
                    diagnostics=replace(diagnostics, kind="oversized_error_object"),
                )
            objects.append(result.structuredContent)
        failures: list[WorkIQFailure] = []
        types: list[str] = []
        for text in texts[:MAX_ERROR_DETAILS]:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                types.append("non_json")
                failures.append(text_failure_details(text))
            except RecursionError:
                types.append("too_deep")
            else:
                types.append(json_type(parsed))
                if isinstance(parsed, dict):
                    objects.append(parsed)
                elif isinstance(parsed, str):
                    failures.append(text_failure_details(parsed))
        truncated = diagnostics.truncated
        for data in objects:
            parent_id = request_id_from(data)
            failures.append(failure_details(data))
            for key in ("results", "errors"):
                rows = data.get(key)
                if isinstance(rows, list):
                    truncated |= len(rows) > MAX_ERROR_DETAILS
                    failures.extend(
                        failure_details(row, parent_id)
                        for row in rows[:MAX_ERROR_DETAILS] if isinstance(row, dict)
                    )
        failures = list(dict.fromkeys(
            item for item in failures if item != WorkIQFailure()
        ))
        primary = next((
            item for item in failures if item.status and not 200 <= item.status < 300
        ), None)
        if primary is None:
            primary = next((
                item for item in failures if item.code
            ), failures[0] if failures else WorkIQFailure())
        if primary.status and not 200 <= primary.status < 300:
            kind, code = "upstream_error", "RequestFailed"
        elif any(200 <= item.status < 300 for item in failures):
            kind, code = "error_flag_with_success_status", "ToolErrorSuccessStatus"
        elif primary.code:
            kind, code = "error_code_without_failure_status", primary.code
        elif objects:
            kind, code = "unrecognized_error_envelope", "ToolErrorUnknownEnvelope"
        elif "non_json" in types:
            kind, code = "non_json_error_text", "ToolErrorNonJsonText"
        elif "too_deep" in types:
            kind, code = "error_json_depth_exceeded", "ToolErrorJsonDepth"
        elif types:
            kind, code = "non_object_error_json", "ToolErrorNonObjectJson"
        elif result.content:
            kind, code = "non_text_error_content", "ToolErrorNonTextContent"
        else:
            kind, code = "missing_error_text", "ToolErrorMissingText"
        raise WorkIQError(
            primary.status, primary.code or code, primary.inner_code,
            request_id=primary.request_id or diagnostics.meta_request_id or transport_id,
            diagnostics=replace(
                diagnostics, kind=kind, json_types=tuple(types),
                failures=tuple(failures[:MAX_ERROR_DETAILS]),
                truncated=truncated or len(failures) > MAX_ERROR_DETAILS,
            ),
        )

    @staticmethod
    def _check_status(result: dict[str, Any], request_id: object = None) -> None:
        status = result.get("statusCode")
        if type(status) is not int or not 100 <= status <= 599:
            raise WorkIQError(0, "InvalidStatus")
        if not 200 <= status < 300:
            details = failure_details(result, correlation_id(request_id))
            raise WorkIQError(
                status, details.code or "RequestFailed", details.inner_code,
                request_id=details.request_id,
            )

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        parsed = urlsplit(path)
        if (
            not path.startswith("/") or path.startswith("//")
            or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
        ):
            raise ValueError("Work IQ requires a relative resource path without a query.")
        entity_url = path + ("?" + urlencode(params) if params else "")
        result = await self._call("fetch", {"entityUrls": [entity_url]})
        rows = result.get("results")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise WorkIQError(0, "InvalidResponse")
        self._check_status(rows[0], result.get("requestId"))
        data = rows[0].get("data")
        if not isinstance(data, dict):
            raise WorkIQError(0, "InvalidResponse")
        if len(json.dumps(data).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise WorkIQError(200, "ResponseTooLarge")
        return data

    async def _list(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        result = await self._get(path, {"$top": str(MAX_ITEMS), **(params or {})})
        items = result.get("value")
        if (
            not isinstance(items, list) or len(items) > MAX_ITEMS
            or any(not isinstance(item, dict) for item in items)
        ):
            raise WorkIQError(200, "InvalidCollection")
        # Work IQ blocks $skip/$skiptoken. Never follow server-provided URLs or
        # pretend a capped result is complete; callers fail closed on has_more.
        return {"items": items, "has_more": bool(result.get("@odata.nextLink"))}

    async def list_meetings(self, start: str, end: str) -> dict[str, Any]:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if not start_time.tzinfo or not end_time.tzinfo:
            raise ValueError("start and end must include a UTC offset.")
        if not timedelta(0) < end_time - start_time <= timedelta(days=31):
            raise ValueError("Choose an increasing date range of at most 31 days.")
        result = await self._list("/me/calendarView", {
            "startDateTime": start, "endDateTime": end,
            "$select": "id,subject,start,end,organizer,isOnlineMeeting,onlineMeeting,webLink",
        })
        result["items"] = [item for item in result["items"] if item.get("isOnlineMeeting")]
        return result

    async def get_event(self, event_id: str) -> dict[str, Any]:
        return await self._get(f"/me/events/{segment(event_id)}", {
            "$select": "id,subject,body,start,end,organizer,attendees,onlineMeeting,webLink",
        })

    async def get_chat_title(self, chat_id: str) -> str:
        # The chat metadata API does not support OData query parameters.
        chat = await self._get(f"/chats/{segment(chat_id)}")
        if chat.get("id") != chat_id:
            raise ValueError("Chat metadata does not match the meeting conversation.")
        title = chat.get("topic")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("The meeting chat has no title for the greeting.")
        return title.strip()

    async def meeting_in_chat(self, join_url: str, chat_id: str) -> dict[str, Any]:
        result = await self.resolve_meeting(join_url)
        matches = [
            item for item in result["items"]
            if (item.get("chatInfo") or {}).get("threadId") == chat_id
        ]
        if result["has_more"] or len(matches) != 1 or not matches[0].get("id"):
            raise ValueError("The meeting could not be uniquely bound to this chat.")
        return matches[0]

    async def invited_event(self, join_url: str, started_at: datetime) -> dict[str, Any]:
        result = await self.list_meetings(
            (started_at - timedelta(days=1)).isoformat(),
            (started_at + timedelta(days=1)).isoformat(),
        )
        if result["has_more"]:
            raise ValueError("Calendar results are incomplete; cannot safely identify the invitation.")
        candidates = []
        for item in result["items"]:
            if (item.get("onlineMeeting") or {}).get("joinUrl") != join_url:
                continue
            start = item.get("start") or {}
            raw_time = start.get("dateTime")
            if not raw_time:
                raise ValueError("The matching invitation has no start time.")
            scheduled = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if scheduled.tzinfo is None:
                if start.get("timeZone") not in {"UTC", "Etc/UTC"}:
                    raise ValueError("The calendar returned an unsupported timezone.")
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if abs(scheduled - started_at) <= timedelta(hours=12):
                candidates.append(item)
        if len(candidates) != 1:
            raise ValueError("No unique invited occurrence matches this actual meeting start.")
        event = await self.get_event(candidates[0]["id"])
        if (event.get("onlineMeeting") or {}).get("joinUrl") != join_url:
            raise ValueError("The meeting invitation changed during lookup.")
        return event

    async def resolve_meeting(self, join_url: str) -> dict[str, Any]:
        parsed = urlsplit(join_url)
        if parsed.scheme != "https" or parsed.hostname not in {"teams.microsoft.com", "teams.live.com"}:
            raise ValueError("Supply the original HTTPS Teams meeting join URL from the calendar event.")
        escaped = join_url.replace("'", "''")
        return await self._list("/me/onlineMeetings", {
            "$filter": f"JoinWebUrl eq '{escaped}'", "$select": "id,chatInfo,joinWebUrl",
        })

    async def list_transcripts(
        self, meeting_id: str, *, call_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"$select": "id,createdDateTime,endDateTime"}
        if call_id is not None:
            escaped = call_id.replace("'", "''")
            params = {"$select": "id,callId", "$filter": f"callId eq '{escaped}'"}
        return await self._list(f"/me/onlineMeetings/{segment(meeting_id)}/transcripts", params)

    async def get_transcript(self, meeting_id: str, transcript_id: str) -> dict[str, Any]:
        path = f"/me/onlineMeetings/{segment(meeting_id)}/transcripts/{segment(transcript_id)}/content"
        result = await self._call("fetch_blob", {"path": path + "?$format=text/vtt"})
        self._check_status(result, result.get("requestId"))
        encoded = result.get("base64Content")
        size = result.get("sizeBytes")
        mime = result.get("contentType")
        if (
            not isinstance(encoded, str)
            or type(size) is not int or size < 0 or size > MAX_RESPONSE_BYTES
            or len(encoded) > 4 * ((MAX_RESPONSE_BYTES + 2) // 3)
        ):
            raise WorkIQError(200, "InvalidBlob")
        if not isinstance(mime, str) or mime.split(";", 1)[0].strip().lower() != "text/vtt":
            raise WorkIQError(200, "UnsupportedTranscriptFormat")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise WorkIQError(200, "InvalidBase64") from None
        if len(content) != size:
            raise WorkIQError(200, "InvalidBlobSize")
        try:
            transcript = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise WorkIQError(200, "InvalidTranscriptEncoding") from None
        return {
            "meeting_id": meeting_id, "transcript_id": transcript_id,
            "format": "text/vtt", "content": transcript,
        }
