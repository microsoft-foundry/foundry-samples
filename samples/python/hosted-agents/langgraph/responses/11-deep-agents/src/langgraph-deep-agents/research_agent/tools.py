"""Load only web search from Foundry Toolbox and record concise progress."""

from __future__ import annotations

import os

from azure.core.credentials import TokenCredential
from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool, tool


@tool
def think_tool(summary: str) -> str:
    """Record a concise factual research-progress summary, not private reasoning.

    Args:
        summary: Evidence obtained, remaining gaps, and the next action. Exclude
            credentials, private records, and private reasoning.

    Returns:
        An acknowledgement of the summary; it does not verify research claims.
    """
    return f"Research progress recorded: {summary}"


async def load_tools(credential: TokenCredential) -> list[BaseTool]:
    """Load web_search without exposing unrelated tools from the same Toolbox.

    Args:
        credential: Caller-owned Azure credential kept alive for tool invocations.

    Returns:
        The configured web_search tool and the local think_tool.

    Raises:
        KeyError: A required project endpoint or Toolbox name is not configured.
        ValueError: The Toolbox does not expose a tool named web_search.
    """
    toolbox = AzureAIProjectToolbox(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        toolbox_name=os.environ["TOOLBOX_NAME"],
        credential=credential,
    )
    search_tools = [
        search_tool
        for search_tool in await toolbox.get_tools()
        if search_tool.name == "web_search"
    ]
    if not search_tools:
        raise ValueError("The configured Foundry Toolbox must expose web_search.")
    return [*search_tools, think_tool]
