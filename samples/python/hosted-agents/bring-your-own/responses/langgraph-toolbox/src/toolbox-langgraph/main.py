"""LangGraph ReAct Agent with Azure AI Foundry Toolbox MCP Support.

This agent connects to an Azure AI Foundry toolbox via MCP and uses it to
respond to user queries.

## Platform-Injected Environment Variables (container-image-spec)

The Foundry platform injects these at runtime:
- `FOUNDRY_PROJECT_ENDPOINT` — project endpoint
- `FOUNDRY_AGENT_TOOLBOX_ENDPOINT` — base URL for toolbox MCP proxy
- `FOUNDRY_AGENT_TOOLBOX_FEATURES` — feature-flag headers for toolbox requests

## User-Defined Variables

- `AZURE_AI_MODEL_DEPLOYMENT_NAME` — chat model deployment name
- `TOOLBOX_ENDPOINT` — full toolbox MCP endpoint URL

## Starting with an Existing Project Endpoint

For local development, set the FOUNDRY_* variables in `.env`:
```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1"
export TOOLBOX_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/mcp?api-version=v1"
```
"""

import asyncio
import logging
import os
import pathlib
import re
from urllib.parse import unquote

from dotenv import load_dotenv

load_dotenv(override=False)

from langgraph.prebuilt import create_react_agent
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses.models import CreateResponse, get_input_expanded
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from langchain_azure_ai.tools import AzureAIProjectToolbox

# ── Agent name and logger ────────────────────────────────────────────────────


def _read_agent_name() -> str:
    try:
        yaml_text = pathlib.Path("agent.yaml").read_text()
        m = re.search(r"^name:\s*(.+)$", yaml_text, re.MULTILINE)
        return m.group(1).strip() if m else "unknown-agent"
    except Exception:
        return "unknown-agent"


AGENT_NAME = _read_agent_name()
logger = logging.getLogger(AGENT_NAME)

# ── LLM ─────────────────────────────────────────────────────────────────────

PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
if not PROJECT_ENDPOINT:
    raise ValueError("FOUNDRY_PROJECT_ENDPOINT must be set")

MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
if not MODEL_DEPLOYMENT_NAME:
    raise ValueError("AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable must be set")

llm = AzureAIOpenAIApiChatModel(
    project_endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
    model=MODEL_DEPLOYMENT_NAME,
    streaming=True,
    # LangGraph manages message history instead of the model service.
    store=False,
)

# ── Toolbox MCP helpers ────────────────────────────────────────────────────

# Toolbox MCP endpoint resolution (in priority order):
#   1. TOOLBOX_ENDPOINT — explicit full URL override (CI / local).
#   2. TOOLBOX_<NAME>_MCP_ENDPOINT — azd auto-injects this per toolbox declared
#      in azure.yaml. Variable name = upper(name) with dashes -> underscores.
#   3. Construct from PROJECT_ENDPOINT + TOOLBOX_NAME as a final fallback.
_TOOLBOX_ENDPOINT_OVERRIDE = os.getenv("TOOLBOX_ENDPOINT", "")
_TOOLBOX_NAME = os.getenv("TOOLBOX_NAME", "")
if _TOOLBOX_ENDPOINT_OVERRIDE:
    TOOLBOX_ENDPOINT = _TOOLBOX_ENDPOINT_OVERRIDE
elif _TOOLBOX_NAME:
    _azd_injected_var = (
        f"TOOLBOX_{_TOOLBOX_NAME.upper().replace('-', '_')}_MCP_ENDPOINT"
    )
    TOOLBOX_ENDPOINT = os.getenv(_azd_injected_var) or (
        f"{PROJECT_ENDPOINT.rstrip('/')}/toolboxes/{_TOOLBOX_NAME}/mcp?api-version=v1"
    )
else:
    TOOLBOX_ENDPOINT = ""

def _toolbox_name_from_endpoint(endpoint: str) -> str | None:
    """Extract toolbox name from endpoint URL path."""
    match = re.search(r"/toolboxes/([^/]+)", endpoint)
    return unquote(match.group(1)) if match else None

SYSTEM_PROMPT = """You are a helpful assistant with access to Azure AI Foundry toolbox tools.

When tool output includes Azure AI Search retrieval metadata, use citation-style
grounding based on result.structuredContent.documents[].

For each citation, prefer:
- title (citation label)
- url (source link)
- score (relevance)

If citations are present, include a brief Sources section in your answer.
Do not invent citation links. If no document metadata is present, answer without
fabricated citations.
"""

# ── Agent creation ──────────────────────────────────────────────────────────


def create_agent(model, tools):
    return create_react_agent(model, tools, prompt=SYSTEM_PROMPT)


async def quickstart():
    """Build and return a LangGraph agent wired to a Foundry toolbox.

    Uses AzureAIProjectToolbox from langchain-azure-ai to resolve and load
    toolbox tools from the project endpoint.
    """
    # Resolve toolbox name: prefer parsing it from the resolved TOOLBOX_ENDPOINT
    # (so an explicit endpoint override wins), fall back to TOOLBOX_NAME env var.
    toolbox_name = _toolbox_name_from_endpoint(TOOLBOX_ENDPOINT) or _TOOLBOX_NAME
    if not toolbox_name:
        raise ValueError(
            "Set TOOLBOX_NAME in the environment or provide TOOLBOX_ENDPOINT "
            "that contains '/toolboxes/<name>' in its path."
        )

    logger.info(f"Connecting to toolbox: {TOOLBOX_ENDPOINT}")
    toolbox = AzureAIProjectToolbox(toolbox_name=toolbox_name)
    tools = await toolbox.get_tools()

    logger.info(f"Loaded {len(tools)} tools from MCP")
    return create_agent(llm, tools), toolbox


def _extract_assistant_text(result: dict) -> str:
    """Best-effort extraction of assistant text from a LangGraph response."""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", "")
        if msg_type != "ai":
            continue

        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            if parts:
                return "\n".join(parts)
    return ""


def _get_input_text(request: CreateResponse) -> str | None:
    """Extract plain text from a CreateResponse input."""
    inp = request.get("input")
    if isinstance(inp, str):
        return inp
    items = get_input_expanded(request)
    for item in items:
        content = item.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for part in content:
                text = part.get("text")
                if text:
                    return text
    return None


server = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)

_agent = None
_mcp_client = None  # Keep MCP client alive to prevent session GC
_agent_lock = asyncio.Lock()


async def _get_agent():
    global _agent, _mcp_client
    if _agent is not None:
        return _agent

    async with _agent_lock:
        if _agent is not None:
            return _agent

        _agent, _mcp_client = await quickstart()
        return _agent


@server.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )

    yield stream.emit_created()
    yield stream.emit_in_progress()

    user_input = _get_input_text(request) or ""
    if not user_input:
        message_item = stream.add_output_item_message()
        yield message_item.emit_added()
        for event in message_item.text_content("No input provided."):
            yield event
        yield message_item.emit_done()
        yield stream.emit_completed()
        return

    try:
        logger.info("Processing request %s", context.response_id)
        agent = await _get_agent()
        result = await asyncio.wait_for(
            agent.ainvoke({"messages": [("user", user_input)]}),
            timeout=240.0,
        )
        assistant_reply = _extract_assistant_text(result)
        if not assistant_reply:
            assistant_reply = "(Agent completed without text response)"
    except asyncio.TimeoutError:
        assistant_reply = "I could not complete this request within the local timeout. Please retry with a simpler prompt."
    except asyncio.CancelledError:
        assistant_reply = "The request was cancelled before completion. Please retry."

    message_item = stream.add_output_item_message()
    yield message_item.emit_added()

    text_content = message_item.add_text_content()
    yield text_content.emit_added()
    yield text_content.emit_delta(assistant_reply)
    yield text_content.emit_text_done()
    yield text_content.emit_done()
    yield message_item.emit_done()

    yield stream.emit_completed()


if __name__ == "__main__":
    server.run()
