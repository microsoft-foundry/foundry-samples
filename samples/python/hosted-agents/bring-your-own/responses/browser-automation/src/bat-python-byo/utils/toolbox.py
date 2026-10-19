# Copyright (c) Microsoft. All rights reserved.

import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from azure.core.credentials import TokenCredential
from azure.identity import get_bearer_token_provider

from utils.utils import public_tool_output


@dataclass
class ToolboxCallResult:
    output: str
    browser_session_id: str | None = None
    live_view_url: str | None = None
    is_error: bool = False
    session_name: str | None = None
    public_output: str | None = None


class ToolboxClient:
    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential,
        api_version: str = "v1",
    ) -> None:
        self._endpoint = endpoint
        self._token_provider = get_bearer_token_provider(
            credential, "https://ai.azure.com/.default"
        )
        self._api_version = api_version
        self._session_id: str | None = None
        self._tools: list[dict[str, Any]] | None = None
        self._initialized = False
        self._lock = threading.RLock()

    def _headers(self) -> dict[str, str]:
        token = self._token_provider()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        response = httpx.post(
            self._endpoint,
            headers=self._headers(),
            json=payload,
            params={"api-version": self._api_version},
            timeout=120,
        )
        response.raise_for_status()
        if session_id := response.headers.get("mcp-session-id"):
            self._session_id = session_id

        body = response.json()
        if error := body.get("error"):
            raise RuntimeError(
                f"MCP {method} failed: {json.dumps(error, ensure_ascii=False)}"
            )
        return body.get("result", {})

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._post(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "browser-automation-byo",
                        "version": "1.0.0",
                    },
                },
            )
            response = httpx.post(
                self._endpoint,
                headers=self._headers(),
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
                params={"api-version": self._api_version},
                timeout=120,
            )
            response.raise_for_status()
            self._initialized = True

    def list_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._tools is None:
                self.initialize()
                self._tools = self._post("tools/list", {}).get("tools", [])
            return self._tools

    def response_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get(
                    "inputSchema",
                    {"type": "object", "properties": {}},
                ),
                "strict": False,
            }
            for tool in self.list_tools()
        ]

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolboxCallResult:
        with self._lock:
            self.initialize()
            result = self._post(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
        content = result.get("content", [])
        text_items = [
            item.get("text", "")
            for item in content
            if item.get("type") == "text"
        ]
        output = "\n".join(item for item in text_items if item)
        if not output:
            output = json.dumps(result, ensure_ascii=False)

        browser_session_id = None
        live_view_url = None
        for text in text_items:
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                browser_session_id = (
                    browser_session_id or value.get("browserSessionId")
                )
                live_view_url = live_view_url or value.get("liveViewUrl")

        if live_view_url:
            sanitized_items = []
            for text in text_items:
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    sanitized_items.append(text)
                    continue
                if isinstance(value, dict):
                    value.pop("liveViewUrl", None)
                    value["note"] = "Live-view URL omitted from model-visible tool output."
                    sanitized_items.append(
                        json.dumps(value, ensure_ascii=False)
                    )
                else:
                    sanitized_items.append(text)
            output = "\n".join(sanitized_items)
            text_items = sanitized_items

        is_error = bool(result.get("isError"))
        live_view_urls = [live_view_url] if live_view_url else []
        public_output = "\n".join(
            public_tool_output(tool_name, text, is_error, live_view_urls)
            for text in text_items if text
        ) if any(text_items) else public_tool_output(
            tool_name, output, is_error, live_view_urls
        )
        return ToolboxCallResult(
            output=output,
            browser_session_id=browser_session_id,
            live_view_url=live_view_url,
            is_error=is_error,
            public_output=public_output,
        )
