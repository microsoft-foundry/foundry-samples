# Copyright (c) Microsoft. All rights reserved.
"""Copilot SDK model/tool loop using a Foundry BYOK provider."""

import logging
import os
import re
from contextlib import AsyncExitStack
from urllib.parse import urlsplit

from azure.ai.agentserver.core import get_request_context
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from copilot import (
    CopilotClient,
    MCPHTTPServerConfig,
    PermissionHandler,
    PreToolUseHookInput,
    PreToolUseHookOutput,
    ProviderConfig,
    SessionEvent,
    SessionHooks,
    ToolSet,
)
from copilot.generated.session_events import (
    ToolExecutionCompleteData,
    ToolExecutionStartData,
)
from opentelemetry import propagate

logger = logging.getLogger("a2a.web_research")


def validate_toolbox_endpoint(endpoint: str, project: str) -> None:
    if (
        "\\" in endpoint
        or "%" in urlsplit(endpoint).path
        or any(segment in {".", ".."} for segment in urlsplit(endpoint).path.split("/"))
    ):
        raise ValueError("TOOLBOX_ENDPOINT contains an unsafe path")
    target, origin = urlsplit(endpoint), urlsplit(project)
    if (
        target.scheme != "https"
        or target.netloc != origin.netloc
        or target.username
        or target.password
        or target.fragment
        or not target.path.startswith(origin.path.rstrip("/") + "/toolboxes/")
        or not target.path.endswith("/mcp")
        or target.query != "api-version=v1"
    ):
        raise ValueError(
            "TOOLBOX_ENDPOINT must be an HTTPS MCP endpoint in this project"
        )


async def ask(
    instructions: str, message: str, *, receipts: list[dict] | None = None
) -> tuple[str, list[dict]]:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must use HTTPS")
    toolbox = os.environ["TOOLBOX_ENDPOINT"]
    validate_toolbox_endpoint(toolbox, endpoint)
    headers = get_request_context().platform_headers()
    propagate.inject(headers)
    calls: dict[str, dict] = {}
    search_count = 0

    def limit_searches(
        _input: PreToolUseHookInput, _invocation: dict[str, str]
    ) -> PreToolUseHookOutput:
        nonlocal search_count
        if search_count >= 2:
            return PreToolUseHookOutput(
                permissionDecision="deny",
                permissionDecisionReason=(
                    "The two-search budget is exhausted. Finish with existing sources "
                    "and mark missing exact-date evidence unverified. Do not retry."
                ),
            )
        search_count += 1
        return PreToolUseHookOutput(permissionDecision="allow")

    def observe(event: SessionEvent) -> None:
        data = event.data
        if (
            isinstance(data, ToolExecutionStartData)
            and data.mcp_tool_name == "web_search"
        ):
            calls[data.tool_call_id] = {
                "tool": "web_search",
                "tool_call_id": data.tool_call_id,
                "success": False,
                "source_urls": [],
            }
            if receipts is not None:
                receipts.append(calls[data.tool_call_id])
        elif isinstance(data, ToolExecutionCompleteData) and data.tool_call_id in calls:
            result = data.result.content if data.result is not None else ""
            urls = sorted(set(re.findall(r'https?://[^\s<>"\\)]+', result)))
            calls[data.tool_call_id].update(
                success=data.success and bool(urls),
                source_urls=urls,
            )
            logger.info(
                "WEB_SEARCH_COMPLETED tool_call_id=%s success=%s source_count=%s",
                data.tool_call_id,
                calls[data.tool_call_id]["success"],
                len(urls),
            )

    async with (
        DefaultAzureCredential(process_timeout=60) as credential,
        AsyncExitStack() as stack,
    ):
        token = await credential.get_token("https://ai.azure.com/.default")
        toolbox_credential: DefaultAzureCredential | ManagedIdentityCredential = (
            credential
        )
        if os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"):
            toolbox_credential = await stack.enter_async_context(
                ManagedIdentityCredential(
                    client_id=os.environ["FOUNDRY_AGENT_INSTANCE_CLIENT_ID"]
                )
            )
        toolbox_token = await toolbox_credential.get_token(
            "https://ai.azure.com/.default"
        )
        toolbox_headers = dict(headers)
        toolbox_headers["Authorization"] = f"Bearer {toolbox_token.token}"
        client = CopilotClient()
        await client.start()
        try:
            session = await client.create_session(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                provider=ProviderConfig(
                    type="azure",
                    base_url=endpoint,
                    wire_api="responses",
                    bearer_token=token.token,
                    headers=headers,
                ),
                reasoning_effort="high",
                system_message={"mode": "replace", "content": instructions},
                mcp_servers={
                    "travel_web": MCPHTTPServerConfig(
                        type="http",
                        url=toolbox,
                        headers=toolbox_headers,
                        tools=["web_search"],
                        timeout=60000,
                    )
                },
                available_tools=ToolSet().add_mcp("*"),
                hooks=SessionHooks(on_pre_tool_use=limit_searches),
                on_event=observe,
                on_permission_request=PermissionHandler.approve_all,
                streaming=False,
                enable_session_store=False,
                enable_config_discovery=False,
                skip_custom_instructions=True,
                enable_skills=False,
            )
            try:
                reply = await session.send_and_wait(message, timeout=180)
                if not any(call["success"] for call in calls.values()):
                    raise RuntimeError(
                        "Web research requires at least one successful web_search call with source URLs"
                    )
                if reply is None or not reply.data.content:
                    raise RuntimeError("Copilot SDK returned no answer")
                return reply.data.content, list(calls.values())
            finally:
                await session.disconnect()
        finally:
            await client.stop()
