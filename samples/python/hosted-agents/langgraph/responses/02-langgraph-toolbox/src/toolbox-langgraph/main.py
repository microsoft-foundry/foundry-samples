# Copyright (c) Microsoft. All rights reserved.

"""LangGraph toolbox agent with Foundry Toolbox tools (Responses protocol).

Exports a LangGraph agent built with `langchain.agents.create_agent` for the
configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint.
Tools are loaded at startup from a Foundry Toolbox via
`langchain_azure_ai.tools.AzureAIProjectToolbox`.

The toolbox exposes Web Search plus the public Microsoft Learn MCP server.
Tool error handling and schema sanitization use the SDK defaults.
"""

from __future__ import annotations

import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from langchain_azure_ai.tools import AzureAIProjectToolbox

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are a helpful assistant with access to Foundry Toolbox tools.

When a tool returns sources (e.g. `web_search` results, or MCP responses
with URLs), ground your answer in those sources and include a brief
"Sources" section listing the titles and URLs of the results you used.
Do not invent citations. If no source URLs are present, answer without
them.
"""


# ── Chat model ───────────────────────────────────────────────────────
def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


# ── Toolbox tools ────────────────────────────────────────────────────
async def _load_toolbox_tools() -> list[BaseTool]:
    toolbox = AzureAIProjectToolbox(toolbox_name=os.environ["TOOLBOX_NAME"])
    tools = await toolbox.get_tools()
    logger.info(
        "Loaded %d tool(s) from Foundry Toolbox '%s':",
        len(tools),
        toolbox.toolbox_name,
    )
    for t in tools:
        logger.info("Loaded toolbox tool: %s", t.name)
    return tools


# ── Graph factory ────────────────────────────────────────────────────
async def create_graph():
    """Load Toolbox tools and create the graph used by the hosting entrypoint."""
    tools = await _load_toolbox_tools()
    return create_agent(_build_chat_model(), tools=tools, system_prompt=SYSTEM_PROMPT)
