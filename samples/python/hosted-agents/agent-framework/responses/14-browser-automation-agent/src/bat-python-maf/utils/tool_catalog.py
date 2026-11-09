from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping
from contextlib import aclosing
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from agent_framework import (
    ChatContext,
    FunctionTool,
    MCPStreamableHTTPTool,
    chat_middleware,
)
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, ResponseStreamEvent
from azure.ai.agentserver.responses.streaming._checkpoint import ResponseCheckpointEvent

_current_catalog: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "response_tool_catalog", default=None
)


@chat_middleware
async def tool_catalog_middleware(
    context: ChatContext, call_next: Callable[[], Awaitable[None]]
) -> None:
    catalog = _current_catalog.get()
    if catalog is None:
        raise RuntimeError("Tool catalog response handling is required.")
    for tool in (context.options or {}).get("tools") or []:
        functions = (
            tool.functions if isinstance(tool, MCPStreamableHTTPTool) else [tool]
        )
        for function in functions:
            if isinstance(function, FunctionTool):
                catalog[function.name] = {
                    "type": "function",
                    "name": function.name,
                    "description": function.description,
                    "parameters": deepcopy(function.parameters()),
                }
    await call_next()


class ToolCatalogResponsesHostServer(ResponsesHostServer):
    async def _handle_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[ResponseStreamEvent | ResponseCheckpointEvent]:
        catalog: dict[str, dict[str, Any]] = {}
        async with aclosing(
            aiter(super()._handle_response(request, context, cancellation_signal))
        ) as events:
            while True:
                token = _current_catalog.set(catalog)
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    return
                finally:
                    _current_catalog.reset(token)
                if isinstance(event, Mapping) and event.get("type") in (
                    "response.completed",
                    "response.incomplete",
                    "response.failed",
                ):
                    event["response"]["tools"] = deepcopy(list(catalog.values()))
                yield event
