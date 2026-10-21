# ruff: noqa: E402
from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from typing import Any

from agent_framework._agents import Agent
from agent_framework._mcp import MCPStreamableHTTPTool
from agent_framework._middleware import chat_middleware, function_middleware
from agent_framework._skills import SkillsProvider
from agent_framework._types import (
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ResponseStream,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from .logging import redact_sensitive_values
from .paths import prompts_root, skill_paths
from .settings import AgentSettings, ScopedAzureCredential
from .tools import (
    clear_live_view_url,
    get_live_view_url,
    make_toolbox_mcp_tool,
    scrub_browser_session_result,
)

logger = logging.getLogger(__name__)
_last_prepended_url: str | None = None


@function_middleware
async def tool_logging_middleware(context: Any, call_next: Any) -> None:
    function_name = getattr(getattr(context, "function", None), "name", "")
    arguments = getattr(context, "arguments", None)
    logger.info(
        "[tool] name=%s arguments=%s",
        function_name,
        redact_sensitive_values(str(arguments)),
    )
    await call_next()
    if function_name.endswith("create_browser_session"):
        scrub_browser_session_result(context.result)
    elif function_name.endswith("close_browser_session"):
        clear_live_view_url()


@chat_middleware
async def live_view_url_inject_middleware(context: Any, call_next: Any) -> None:
    await call_next()
    global _last_prepended_url

    if context.stream and isinstance(context.result, ResponseStream):
        original_stream = context.result

        async def _inject_url_stream() -> AsyncIterable[ChatResponseUpdate]:
            global _last_prepended_url
            has_text = False
            async for update in original_stream:
                live_view_url = get_live_view_url()
                if live_view_url and _last_prepended_url != live_view_url:
                    yield ChatResponseUpdate(
                        contents=[
                            Content.from_text(
                                text=f"🔴 Created Browser Session: [Live View]({live_view_url})\n\n"
                            )
                        ],
                        role="assistant",
                    )
                    _last_prepended_url = live_view_url
                yield update
                if not has_text and update.contents:
                    has_text = any(
                        getattr(content, "type", None) == "text"
                        for content in update.contents
                    )

            live_view_url = get_live_view_url()
            if live_view_url and (has_text or _last_prepended_url != live_view_url):
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_text(
                            text=f"\n\n🔴 [Browser Live View]({live_view_url})\n"
                        )
                    ],
                    role="assistant",
                    finish_reason="stop",
                )
                _last_prepended_url = live_view_url

        context.result = ResponseStream(
            _inject_url_stream(), finalizer=ChatResponse.from_updates
        )
    elif isinstance(context.result, ChatResponse):
        from agent_framework._types import Message

        live_view_url = get_live_view_url()
        if not live_view_url or _last_prepended_url == live_view_url:
            return
        context.result.messages.append(
            Message("assistant", [f"\n\n🔴 [Browser Live View]({live_view_url})"])
        )
        _last_prepended_url = live_view_url


def build_agent(settings: AgentSettings) -> tuple[Agent, MCPStreamableHTTPTool]:
    default_credential = DefaultAzureCredential()
    credential = ScopedAzureCredential(
        credential=default_credential,
        scope=settings.azure_scope,
    )
    client = FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model,
        credential=credential,
    )
    toolbox_mcp_tool = make_toolbox_mcp_tool(settings, default_credential)
    skills_provider = SkillsProvider.from_paths(
        skill_paths=skill_paths(),
        disable_load_skill_approval=True,
        disable_run_skill_script_approval=True,
    )
    instructions = (prompts_root() / "base.md").read_text(encoding="utf-8").strip()

    agent = Agent(
        client=client,
        name="browser-automation-python-maf-sample-foundry",
        instructions=instructions,
        tools=[toolbox_mcp_tool],
        context_providers=[skills_provider],
        middleware=[tool_logging_middleware, live_view_url_inject_middleware],
        default_options={"store": False},
    )
    return agent, toolbox_mcp_tool
