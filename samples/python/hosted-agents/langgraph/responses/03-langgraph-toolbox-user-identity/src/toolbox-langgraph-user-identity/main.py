# Copyright (c) Microsoft. All rights reserved.

"""LangGraph toolbox agent with user-identity MCP tools (Responses protocol).

Exports a LangGraph agent built with `langchain.agents.create_agent` for the
configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint.
Tools are loaded at startup from a Foundry Toolbox via
`langchain_azure_ai.tools.AzureAIProjectToolbox`.

The toolbox contains WorkIQ Mail, WorkIQ Calendar, and GitHub MCP
connections that authenticate on behalf of the calling user.
Tool error handling and schema sanitization use the SDK defaults.
"""

from __future__ import annotations

import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are a helpful assistant with access to tools through
Foundry Toolbox, including the calling user's mail, calendar, and GitHub tools
when configured.

Use a matching tool whenever the request depends on the user's data. When a code
interpreter is available, use it to perform calculations and base your answer on
its result rather than doing arithmetic yourself or estimating the answer.
Summarize only the information needed to answer the request. When a tool returns
source URLs, include a brief "Sources" section listing the titles and URLs you
used. Do not invent citations. If OAuth consent is required, return the complete
consent URL verbatim so the user can authorize the connection.
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
    for tool in tools:
        logger.info("Loaded toolbox tool: %s", tool.name)
    return tools


# ── Graph factory ────────────────────────────────────────────────────
async def create_graph():
    """Load Toolbox tools and create the graph used by the hosting entrypoint."""
    tools = await _load_toolbox_tools()
    return create_agent(_build_chat_model(), tools=tools, system_prompt=SYSTEM_PROMPT)
