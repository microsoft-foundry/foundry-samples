# Copyright (c) Microsoft. All rights reserved.

"""Responses-hosted support triage with SDK handoffs and a local MCP server."""

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import mcp
from agents import Agent, Model, OpenAIResponsesModel, RunConfig, RunHooks, Runner
from agents.mcp import MCPServerStdio
from agents.mcp.util import ToolFilterContext
from agents.stream_events import RawResponsesStreamEvent
from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from mcp.types import Tool
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputParam

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("support_triage")

app = ResponsesAgentServerHost()


def _messages_from_items(
    items: Sequence[Mapping[str, Any]], *, strict: bool
) -> ResponseInputParam:
    messages: ResponseInputParam = []
    for item in items:
        if item.get("type") != "message" or item.get("role") not in ("user", "assistant"):
            if strict:
                raise ValueError("Only user and assistant text messages are supported.")
            continue

        content = item.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") in ("input_text", "output_text")
                    and isinstance(part.get("text"), str)
                ):
                    text_parts.append(part["text"])
                elif strict:
                    raise ValueError("Only text message content is supported.")
            text = "\n".join(text_parts)
        else:
            if strict:
                raise ValueError("Only text message content is supported.")
            continue

        if not text.strip():
            continue
        if item["role"] == "user":
            messages.append({"role": "user", "content": text})
        else:
            messages.append({"role": "assistant", "content": text})
    return messages


def _build_input_items(
    history: Sequence[Mapping[str, Any]], current: Sequence[Mapping[str, Any]]
) -> ResponseInputParam:
    messages = _messages_from_items(history, strict=False)
    current_messages = _messages_from_items(current, strict=True)
    if not any(item.get("role") == "user" for item in current_messages):
        raise ValueError("The request must include a non-empty user text message.")
    messages.extend(current_messages)
    return messages


def _allowed_tool(context: ToolFilterContext, tool: Tool) -> bool:
    if context.agent.name == "Triage":
        return tool.name == "lookup_case"
    return tool.name == "get_knowledge_article"


def _build_agents(server: MCPServerStdio, model: Model) -> Agent:
    billing = Agent(
        name="Billing Specialist",
        handoff_description="Explain a billing case using its knowledge article.",
        instructions=(
            "You are the billing specialist for a fictional SaaS support desk. "
            "Use the case details supplied by triage. Call get_knowledge_article "
            "with the case's article_id before answering. Explain the case and "
            "the article's guidance, and cite the article ID. If the article is "
            "not found, say so. Never claim to change an account or issue a refund."
        ),
        model=model,
        mcp_servers=[server],
    )
    technical = Agent(
        name="Technical Specialist",
        handoff_description="Diagnose a technical case using its knowledge article.",
        instructions=(
            "You are the technical specialist for a fictional SaaS support desk. "
            "Use the case details supplied by triage. Call get_knowledge_article "
            "with the case's article_id before answering. Explain the issue and "
            "the article's next steps, and cite the article ID. If the article "
            "is not found, say so. Never claim to make changes to an account."
        ),
        model=model,
        mcp_servers=[server],
    )
    return Agent(
        name="Triage",
        instructions=(
            "You triage a fictional SaaS support desk. Ask for a case ID if none "
            "is supplied or available in the conversation. Always call lookup_case "
            "before answering a case question. If the case is not found, say "
            "'case not found' and do not hand off. For a found billing case, "
            "hand off to Billing Specialist; for a found technical case, hand "
            "off to Technical Specialist. Do not invent case details, answer "
            "specialist questions yourself, or claim to take account actions."
        ),
        model=model,
        mcp_servers=[server],
        handoffs=[billing, technical],
    )


class TriageHooks(RunHooks):
    async def on_handoff(self, context, from_agent, to_agent):
        logger.info("support triage handoff: %s -> %s", from_agent.name, to_agent.name)

    async def on_tool_start(self, context, agent, tool):
        logger.info("support triage tool: %s (%s)", tool.name, agent.name)


async def _cancel_when_requested(signal: asyncio.Event, result) -> None:
    await signal.wait()
    result.cancel()


async def _run_triage(
    input_items: ResponseInputParam,
    cancellation_signal: asyncio.Event,
    chunks: asyncio.Queue[str | None],
    *,
    model: Model | None = None,
) -> None:
    if cancellation_signal.is_set():
        raise asyncio.CancelledError

    async with AsyncExitStack() as stack:
        if model is None:
            endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
            deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
            credential = await stack.enter_async_context(DefaultAzureCredential())
            token_provider = get_bearer_token_provider(
                credential, "https://ai.azure.com/.default"
            )
            client = await stack.enter_async_context(
                AsyncOpenAI(base_url=f"{endpoint}/openai/v1", api_key=token_provider)
            )
            model = OpenAIResponsesModel(model=deployment, openai_client=client)

        server = await stack.enter_async_context(
            MCPServerStdio(
                params={
                    "command": sys.executable,
                    "args": [str(Path(__file__).with_name("case_server.py"))],
                    # MCP filters the child environment; hosted code builds can
                    # expose dependencies through the parent's Python path.
                    "env": {
                        "PYTHONPATH": str(Path(mcp.__file__).resolve().parent.parent),
                        "PYTHONNOUSERSITE": "1",
                    },
                },
                name="fictional-support",
                tool_filter=_allowed_tool,
                failure_error_function=None,
            )
        )
        result = Runner.run_streamed(
            _build_agents(server, model),
            input=input_items,
            hooks=TriageHooks(),
            run_config=RunConfig(tracing_disabled=True),
        )
        events = result.stream_events()
        cancellation_task = asyncio.create_task(
            _cancel_when_requested(cancellation_signal, result)
        )
        try:
            async for event in events:
                if cancellation_signal.is_set():
                    raise asyncio.CancelledError
                if isinstance(event, RawResponsesStreamEvent):
                    raw = event.data
                    if raw.type == "response.output_text.delta" and raw.delta:
                        chunks.put_nowait(raw.delta)
            if cancellation_signal.is_set():
                raise asyncio.CancelledError
        finally:
            cancellation_task.cancel()
            if not result.is_complete:
                result.cancel()
            try:
                await events.aclose()
            finally:
                tasks = [cancellation_task]
                if result.run_loop_task is not None:
                    tasks.append(result.run_loop_task)
                for outcome in await asyncio.gather(*tasks, return_exceptions=True):
                    if isinstance(outcome, Exception):
                        raise outcome


async def _stream_triage(
    input_items: ResponseInputParam,
    cancellation_signal: asyncio.Event,
    *,
    model: Model | None = None,
) -> AsyncIterator[str]:
    # Keep MCP's AnyIO scopes in one task even if the host switches stream consumers.
    chunks: asyncio.Queue[str | None] = asyncio.Queue()
    producer = asyncio.create_task(
        _run_triage(input_items, cancellation_signal, chunks, model=model)
    )
    producer.add_done_callback(lambda _: chunks.put_nowait(None))
    try:
        while (chunk := await chunks.get()) is not None:
            yield chunk
        await producer
    finally:
        if not producer.done():
            producer.cancel()
        cleanup = asyncio.gather(producer, return_exceptions=True)
        cancelled = False
        while True:
            try:
                (outcome,) = await asyncio.shield(cleanup)
                break
            except asyncio.CancelledError:
                cancelled = True
        if isinstance(outcome, Exception):
            raise outcome
        if cancelled:
            raise asyncio.CancelledError


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    history = await context.get_history()
    current = await context.get_input_items()
    input_items = _build_input_items(history, current)
    return TextResponse(
        context,
        request,
        text=_stream_triage(input_items, cancellation_signal),
    )


if __name__ == "__main__":
    app.run()
