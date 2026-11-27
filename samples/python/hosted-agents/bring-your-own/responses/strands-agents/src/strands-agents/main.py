# Copyright (c) Microsoft. All rights reserved.

"""Strands Agents on Microsoft Foundry Hosted Agents (Responses protocol).

A cloud-migration assistant built with the Strands Agents SDK:

* The orchestrator and the specialist run on a Foundry model deployment through
  Strands' OpenAI Responses provider, authenticated with Microsoft Entra ID
  (no API keys).
* ``service_mapper`` is a specialist Strands agent exposed to the orchestrator
  with ``Agent.as_tool()`` (the agents-as-tools pattern).
* The orchestrator grounds answers with the Microsoft Learn MCP server through
  Strands' ``MCPClient``.
* Conversation history is managed by the Foundry Responses protocol and replayed
  into Strands on each turn.
"""

import asyncio
import logging
import os

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI
from strands import Agent
from strands.models.openai_responses import OpenAIResponsesModel
from strands.tools.mcp import MCPClient

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("strands_agents_sample")

LEARN_MCP_URL = os.environ.get("LEARN_MCP_URL", "https://learn.microsoft.com/api/mcp")

_token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
_openai_client = AsyncOpenAI(
    base_url=f"{os.environ.get('FOUNDRY_PROJECT_ENDPOINT', '').rstrip('/')}/openai/v1",
    api_key=_token_provider,
)
_model = OpenAIResponsesModel(
    client=_openai_client,
    model_id=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
)

_MAPPER_PROMPT = """You map AWS services to their closest Microsoft Azure equivalents.
For each AWS service you are given, return one line in the form
`<AWS service> -> <Azure service>: <one-sentence note on the main difference>`.
Only map services; do not give migration plans."""

_ORCHESTRATOR_PROMPT = """You are a cloud migration assistant that helps teams move
workloads from AWS to Microsoft Azure.

- Always call the `service_mapper` tool to map AWS services to Azure services.
- Use the Microsoft Learn `microsoft_docs_search` tool to ground recommendations,
  and cite at most two learn.microsoft.com links.
- Keep answers under 200 words and name the Azure services explicitly."""

app = ResponsesAgentServerHost()


def _to_strands_messages(history: list) -> list[dict]:
    """Convert Responses protocol history items into Strands messages."""
    messages: list[dict] = []
    for item in history:
        for part in item.get("content") or []:
            text = part.get("text")
            if not text:
                continue
            if part.get("type") == "input_text":
                messages.append({"role": "user", "content": [{"text": text}]})
            elif part.get("type") == "output_text":
                messages.append({"role": "assistant", "content": [{"text": text}]})
    return messages


def _build_agent(history: list) -> Agent:
    """Build a per-request orchestrator so concurrent requests never share agent state."""
    service_mapper = Agent(
        name="service_mapper",
        description="Maps AWS services to their closest Azure equivalents.",
        model=_model,
        system_prompt=_MAPPER_PROMPT,
        callback_handler=None,
    )
    learn_mcp = MCPClient(url=LEARN_MCP_URL, tool_filters={"allowed": ["microsoft_docs_search"]})
    return Agent(
        name="migration_assistant",
        model=_model,
        system_prompt=_ORCHESTRATOR_PROMPT,
        messages=_to_strands_messages(history),
        tools=[service_mapper.as_tool(), learn_mcp],
        callback_handler=None,
    )


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    user_message = (await context.get_input_text() or "").strip() or "What can you help me with?"
    history = await context.get_history()
    agent = await asyncio.to_thread(_build_agent, history)

    async def stream_text():
        logged_tool_uses: set[str] = set()
        try:
            async for event in agent.stream_async(user_message):
                tool_use = event.get("current_tool_use") or {}
                if tool_use.get("toolUseId") and tool_use["toolUseId"] not in logged_tool_uses:
                    logged_tool_uses.add(tool_use["toolUseId"])
                    logger.info("strands tool call: %s", tool_use.get("name"))
                text = event.get("data")
                if isinstance(text, str) and text:
                    yield text
        except Exception:
            logger.exception("Strands agent run failed")
            yield "Sorry, the agent hit an error while answering. Check the agent logs for details."
        finally:
            await asyncio.to_thread(agent.cleanup)

    return TextResponse(context, request, text=stream_text())


if __name__ == "__main__":
    app.run()
