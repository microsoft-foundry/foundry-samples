# Copyright (c) Microsoft. All rights reserved.

"""Getting-started: Claude Agent SDK with Foundry auth and invocations protocol."""

import logging
import os
import json
from dataclasses import asdict
from typing import Optional
from urllib.parse import urlparse

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse

from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from claude_agent_sdk import ClaudeAgentOptions, query

logger = logging.getLogger(__name__)

project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
resource_name = urlparse(project_endpoint).netloc.split(".")[0]
os.environ["ANTHROPIC_FOUNDRY_BASE_URL"] = f"https://{resource_name}.services.ai.azure.com/anthropic"

app = InvocationAgentServerHost()

# --- Optional Foundry Toolbox integration -----------------------------------
# Claude Agent SDK's `ClaudeAgentOptions.mcp_servers` natively speaks Streamable
# HTTP MCP, so `tools/call` round-trips against the toolbox are handled by the
# SDK itself. This sample *consumes* an already-provisioned toolbox; it does
# not create or configure one (see `azd ai toolbox create` / the Foundry
# Toolbox docs for provisioning).
#
# This integration is inert unless TOOLBOX_ENDPOINT or TOOLBOX_NAME is set.
# Once either is set, toolbox integration is *required* to succeed: any
# discovery, auth, or allowlist-validation failure raises and fails the
# invocation rather than silently continuing without toolbox tools. Only an
# *unset* toolbox preserves the base (no-toolbox) behavior.
TOOLBOX_SERVER_LABEL = "foundry-toolbox"
_TOOLBOX_API_VERSION = "v1"
_TOOLBOX_SCOPE = "https://ai.azure.com/.default"
# Header documented by the Foundry Toolboxes (preview) protocol reference.
_TOOLBOX_FEATURES = "Toolboxes=V1Preview"

# `get_bearer_token_provider` itself is safe to share across requests/threads:
# calling it is what produces a fresh token (it caches/refreshes internally),
# it never carries request-specific state, and it mutates no shared headers.
# Construction is deliberately lazy (built on first use, not at import time):
# `DefaultAzureCredential()` probes several credential sources and is slow
# (seconds), so the base/no-toolbox path -- and every test that doesn't
# exercise the toolbox path -- must not pay that cost or require live Azure
# credentials just to import this module.
_toolbox_token_provider = None


def _get_toolbox_token_provider():
    global _toolbox_token_provider
    if _toolbox_token_provider is None:
        _toolbox_token_provider = get_bearer_token_provider(DefaultAzureCredential(), _TOOLBOX_SCOPE)
    return _toolbox_token_provider


def _ensure_api_version(url: str) -> str:
    if "api-version=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}api-version={_TOOLBOX_API_VERSION}"


def _resolve_toolbox_endpoint() -> Optional[str]:
    endpoint = os.environ.get("TOOLBOX_ENDPOINT", "").strip()
    if endpoint:
        return _ensure_api_version(endpoint)

    toolbox_name = os.environ.get("TOOLBOX_NAME", "").strip()
    if not toolbox_name:
        return None

    return _ensure_api_version(f"{project_endpoint}/toolboxes/{toolbox_name}/mcp")


def _resolve_allowed_tools() -> list[str]:
    """Explicit, user-configured read-only allowlist of toolbox tool names.

    Discovery never grants permissions by itself: every name configured here
    must also be returned by the toolbox's own `tools/list` response, or the
    invocation fails (see `_validate_allowed_tools`). A tool the toolbox
    exposes but that is *not* listed here (for example a write/mutating tool)
    is never added to `allowed_tools` and so is never callable.
    """
    raw = os.environ.get("TOOLBOX_ALLOWED_TOOLS", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


TOOLBOX_ENDPOINT = _resolve_toolbox_endpoint()
TOOLBOX_ALLOWED_TOOLS = _resolve_allowed_tools()

if TOOLBOX_ENDPOINT and not TOOLBOX_ALLOWED_TOOLS:
    raise EnvironmentError(
        "TOOLBOX_ENDPOINT/TOOLBOX_NAME is set but TOOLBOX_ALLOWED_TOOLS is empty. "
        "Set TOOLBOX_ALLOWED_TOOLS to a comma-separated list of toolbox tool "
        "names to expose, e.g. TOOLBOX_ALLOWED_TOOLS=web_search."
    )


def _toolbox_headers() -> dict[str, str]:
    """Build request-local headers for one invocation's toolbox calls.

    Builds a brand-new dict every call (never a shared/cached dict, never
    mutated in place) so nothing leaks across concurrent requests. The bearer
    token is minted fresh here and reused for both the discovery call and the
    native `mcp_servers` HTTP config within *this* invocation -- it is not
    re-minted per outbound call. `claude_agent_sdk`'s MCP HTTP transport
    (`McpHttpServerConfig`/`McpSSEServerConfig`) does not expose a mid-stream
    token-refresh hook, so if a single invocation genuinely outlives the
    token's lifetime the subsequent MCP call fails with 401 and surfaces as an
    invocation error -- it is not silently retried or swallowed.

    The per-request `x-agent-foundry-call-id` header (via
    `get_request_context().platform_headers()`) is forwarded on both the
    discovery call and the native MCP config, per the Foundry container
    protocol (outbound calls to Toolboxes/MCP routed through
    `FOUNDRY_PROJECT_ENDPOINT` must carry it).
    """
    token = _get_toolbox_token_provider()()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Foundry-Features": _TOOLBOX_FEATURES,
    }
    headers.update(get_request_context().platform_headers())
    return headers


async def _discover_toolbox_tools(endpoint: str, headers: dict[str, str]) -> list[str]:
    """Request-local MCP `tools/list` call used only to validate the allowlist.

    Never cached across requests: discovery must reflect the toolbox's current
    state so a stale cached name list can't be used to approve a tool that no
    longer exists (or hide one that now does).
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    if "error" in body:
        raise RuntimeError(f"Toolbox tools/list failed: {body['error']}")

    tool_names = [tool["name"] for tool in body.get("result", {}).get("tools", []) if "name" in tool]
    if not tool_names:
        raise RuntimeError(f"Toolbox at {endpoint} returned no tools.")
    return tool_names


def _validate_allowed_tools(configured: list[str], discovered: list[str]) -> list[str]:
    """Validate the configured allowlist against discovered tool names.

    Every name in `configured` must appear in `discovered`, or the invocation
    fails outright -- a missing/unknown name is a configuration error, not
    something to skip silently. Discovery can only narrow access (prove a
    configured name exists); it can never expand it.
    """
    discovered_set = set(discovered)
    unknown = sorted(name for name in configured if name not in discovered_set)
    if unknown:
        raise RuntimeError(
            f"TOOLBOX_ALLOWED_TOOLS references tool(s) not returned by toolbox "
            f"discovery: {unknown}. Discovered tools: {sorted(discovered_set)}."
        )
    return configured


@app.invoke_handler
async def handle_invoke(request: Request) -> Response:
    try:
        input_text = (await request.body()).decode("utf-8").strip()
        if not input_text:
            raise ValueError("empty request body")
    except (UnicodeDecodeError, ValueError):
        return PlainTextResponse(
            status_code=400,
            content="Request body must be a non-empty plain text string.",
        )

    async def event_generator():
        prompt = input_text
        option_kwargs = dict(
            # "dontAsk" denies any tool call that isn't pre-approved via
            # `allowed_tools` instead of prompting -- this is a fail-closed
            # mode, distinct from (and never replaced by) the blanket
            # "bypassPermissions" mode, which would allow every tool.
            permission_mode="dontAsk",
            model=os.environ["ANTHROPIC_MODEL"],
            include_partial_messages=True,
            system_prompt=(
                "You are a helpful coding assistant running in a hosted invocations endpoint. "
                "Prefer concise, actionable responses."
            ),
        )

        if TOOLBOX_ENDPOINT:
            try:
                headers = _toolbox_headers()
                discovered = await _discover_toolbox_tools(TOOLBOX_ENDPOINT, headers)
                allowed = _validate_allowed_tools(TOOLBOX_ALLOWED_TOOLS, discovered)
                option_kwargs["mcp_servers"] = {
                    TOOLBOX_SERVER_LABEL: {
                        "type": "http",
                        "url": TOOLBOX_ENDPOINT,
                        "headers": headers,
                    }
                }
                option_kwargs["allowed_tools"] = [
                    f"mcp__{TOOLBOX_SERVER_LABEL}__{name}" for name in allowed
                ]
            except Exception as ex:
                # TOOLBOX_ENDPOINT/TOOLBOX_NAME is configured: any discovery,
                # auth, or allowlist failure here is a hard invocation failure,
                # never a silent fallback to no-toolbox behavior.
                logger.error("Toolbox integration failed: %s", ex)
                error_payload = json.dumps({"error": f"toolbox integration failed: {ex}"})
                yield f"data: {error_payload}\n\n".encode("utf-8")
                return

        options = ClaudeAgentOptions(**option_kwargs)

        try:
            async for message in query(prompt=prompt, options=options):
                yield f"data: {json.dumps(asdict(message))}\n\n".encode("utf-8")
        except Exception as ex:
            error_payload = json.dumps({"error": str(ex)})
            yield f"data: {error_payload}\n\n".encode("utf-8")
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run()
