# Copyright (c) Microsoft. All rights reserved.
"""Authenticated model and managed MCP transport; no direct remote A2A client."""

import json
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2 as httpx
from azure.ai.agentserver.core import get_request_context
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import propagate, trace

TRACER = trace.get_tracer("a2a.travel")


class FoundryServices:
    def __init__(self, project: str, model: str, toolbox: str) -> None:
        self.project = project.rstrip("/")
        parsed = urlsplit(self.project)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+", parsed.path)
        ):
            raise ValueError(
                "Use an HTTPS Foundry project endpoint without credentials or query"
            )
        if not re.fullmatch(
            re.escape(self.project)
            + r"/toolboxes/[A-Za-z0-9_-]+/(?:versions/[A-Za-z0-9_-]+/)?mcp\?api-version=v1",
            toolbox,
        ):
            raise ValueError(
                "TOOLBOX_ENDPOINT must be an MCP endpoint in the same project"
            )
        if not model:
            raise ValueError("Specify an existing model deployment")
        self.model = model
        self.toolbox = toolbox
        self.credential = DefaultAzureCredential()
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15))

    async def close(self) -> None:
        await self.http.aclose()
        await self.credential.close()

    async def headers(self) -> dict[str, str]:
        token = await self.credential.get_token("https://ai.azure.com/.default")
        headers = {"Authorization": "Bearer " + token.token}
        propagate.inject(headers)
        # Preserve trusted platform delegation context, never the incoming Authorization.
        headers.update(get_request_context().platform_headers())
        return headers

    async def model_response(self, request: dict[str, Any]) -> dict[str, Any]:
        with TRACER.start_as_current_span("travel.model"):
            response = await self.http.post(
                self.project + "/openai/v1/responses",
                headers=await self.headers(),
                json={
                    "model": self.model,
                    "reasoning": {"effort": "minimal"},
                    "max_output_tokens": 2400,
                    "store": False,
                    **request,
                },
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("status") != "completed":
                raise RuntimeError("Model response did not complete")
            if not isinstance(result.get("output"), list):
                raise TypeError("Model response is missing output")
            return result

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
