# Copyright (c) Microsoft. All rights reserved.
"""Authenticated model and managed MCP transport; no direct remote A2A client."""

import json
import re
from typing import Any
from uuid import uuid4

from model import ModelClient
from opentelemetry import trace

TRACER = trace.get_tracer("a2a.travel")


class FoundryServices(ModelClient):
    def __init__(self, project: str, model: str, toolbox: str) -> None:
        if not re.fullmatch(
            re.escape(project.rstrip("/"))
            + r"/toolboxes/[A-Za-z0-9_-]+/(?:versions/[A-Za-z0-9_-]+/)?mcp\?api-version=v1",
            toolbox,
        ):
            raise ValueError(
                "TOOLBOX_ENDPOINT must be an MCP endpoint in the same project"
            )
        super().__init__(project, model)
        self.toolbox = toolbox

    async def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid4().hex
        with TRACER.start_as_current_span("travel.toolbox." + method):
            headers = await self.headers()
            headers["Accept"] = "application/json, text/event-stream"
            response = await self.http.post(
                self.toolbox,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
            )
            response.raise_for_status()
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip()
            )
            if content_type == "application/json":
                messages = [response.json()]
            elif content_type == "text/event-stream":
                messages = []
                for event in response.text.replace("\r\n", "\n").split("\n\n"):
                    data = "\n".join(
                        line[5:].lstrip()
                        for line in event.splitlines()
                        if line.startswith("data:")
                    )
                    if data:
                        messages.append(json.loads(data))
            else:
                raise RuntimeError(
                    "Unsupported Toolbox response content type: " + content_type
                )
            matching = [
                item
                for item in messages
                if isinstance(item, dict) and item.get("id") == request_id
            ]
            if len(matching) != 1 or matching[0].get("jsonrpc") != "2.0":
                raise RuntimeError(
                    "Toolbox did not return one matching JSON-RPC response"
                )
            result = matching[0]
            if "error" in result:
                raise RuntimeError(
                    "Toolbox operation failed: " + json.dumps(result["error"])
                )
            if not isinstance(result.get("result"), dict) or result["result"].get(
                "isError"
            ):
                raise RuntimeError(
                    "Toolbox operation returned an error or invalid result"
                )
            return result["result"]
