# Copyright (c) Microsoft. All rights reserved.

"""LangGraph concierge agent that delegates to a remote A2A agent (Responses protocol).

Hosts a LangGraph agent built with `langchain.agents.create_agent` on Foundry
over the Responses protocol, using
`langchain_azure_ai.agents.hosting.ResponsesHostServer`.

Delegation tools are loaded at startup from a Foundry **Toolbox** over MCP via
`langchain_mcp_adapters.client.MultiServerMCPClient`. The toolbox (declared in
agent.manifest.yaml) exposes an `a2a_preview` tool that proxies calls to a
remote A2A-compatible agent — the sibling `a2a-executor` math expert — through a
`RemoteA2A` connection. The LLM decides when to delegate.

Conversation state is managed server-side by the platform via
`previous_response_id` — no application-side session storage is needed.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


# ── Chat model ───────────────────────────────────────────────────────
def _build_chat_model() -> AzureAIOpenAIApiChatModel:
    return AzureAIOpenAIApiChatModel(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o"),
        # LangGraph manages message history instead of the model service.
        store=False,
    )


# ── Toolbox (A2A delegation) over MCP ─────────────────────────────────
class _ToolboxAuth(httpx.Auth):
    """Injects a fresh Entra bearer token on every toolbox MCP request.

    The toolbox MCP endpoint is authenticated with a short-lived Entra token.
    Using an `httpx.Auth` (rather than a static `Authorization` header) means
    the token is re-minted per request, so long-lived agents don't fail once
    the initial token expires.
    """

    def __init__(self, token_provider) -> None:
        self._get_token = token_provider

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


def _toolbox_mcp_url() -> str:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    toolbox_name = os.environ["TOOLBOX_NAME"]
    return f"{project_endpoint}/toolboxes/{toolbox_name}/mcp?api-version=v1"


async def _load_toolbox_tools() -> list[BaseTool]:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    client = MultiServerMCPClient(
        {
            "a2a-delegation": {
                "transport": "streamable_http",
                "url": _toolbox_mcp_url(),
                "auth": _ToolboxAuth(token_provider),
            }
        }
    )
    tools = await client.get_tools()
    logger.info(
        "Loaded %d tool(s) from Foundry Toolbox '%s' for A2A delegation:",
        len(tools),
        os.environ["TOOLBOX_NAME"],
    )
    for t in tools:
        logger.info("Loaded delegation tool: %s", t.name)
    return tools


_INSTRUCTIONS = (
    "You are a friendly concierge agent. When the user asks a question that is "
    "best answered by a specialist, delegate the request to the remote agent "
    "exposed through the A2A delegation tool, then summarize the result back to "
    "the user in a concise, friendly tone. If no remote skill is relevant, answer "
    "directly."
)


# ── Entrypoint ───────────────────────────────────────────────────────
def main() -> None:
    tools = asyncio.run(_load_toolbox_tools())
    graph = create_agent(
        _build_chat_model(),
        tools=tools,
        system_prompt=_INSTRUCTIONS,
    )

    port = int(os.environ.get("PORT", "8088"))
    ResponsesHostServer(graph).run(port=port)


if __name__ == "__main__":
    main()
