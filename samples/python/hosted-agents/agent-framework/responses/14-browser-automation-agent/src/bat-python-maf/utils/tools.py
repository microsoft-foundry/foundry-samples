from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from agent_framework._mcp import MCPStreamableHTTPTool
from agent_framework._types import Content
from azure.identity import get_bearer_token_provider

from .settings import AgentSettings

logger = logging.getLogger(__name__)

_live_view_url: str | None = None


class ToolboxAuth(httpx.Auth):
    def __init__(self, token_provider: Any):
        self._token_provider = token_provider

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token_provider()}"
        yield request


def get_live_view_url() -> str | None:
    return _live_view_url


def clear_live_view_url() -> None:
    global _live_view_url
    _live_view_url = None


def resolve_toolbox_endpoint(settings: AgentSettings) -> str:
    return (
        f"{settings.project_endpoint.rstrip('/')}/toolboxes/"
        f"{settings.toolbox_name}/mcp?api-version=v1"
    )


def scrub_browser_session_result(contents: list[Content]) -> None:
    for content in contents:
        if content.type != "text" or not content.text:
            continue
        try:
            value = json.loads(content.text)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or not value.get("browserSessionId"):
            continue
        live_view_url = value.pop("liveViewUrl", None)
        if isinstance(live_view_url, str) and live_view_url:
            global _live_view_url
            _live_view_url = live_view_url
            value["note"] = "The live view link is delivered directly to the user."
        content.text = json.dumps(value, ensure_ascii=False)


def make_toolbox_mcp_tool(
    settings: AgentSettings, credential: Any
) -> MCPStreamableHTTPTool:
    token_provider = get_bearer_token_provider(credential, settings.azure_scope)
    http_client = httpx.AsyncClient(
        auth=ToolboxAuth(token_provider),
        timeout=settings.mcp_timeout_seconds,
    )
    return MCPStreamableHTTPTool(
        name=settings.toolbox_name,
        url=resolve_toolbox_endpoint(settings),
        http_client=http_client,
        request_timeout=settings.mcp_timeout_seconds,
        load_prompts=False,
        description="Azure Playwright browser automation tools.",
        approval_mode="never_require",
    )
