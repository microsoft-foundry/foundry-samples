# Copyright (c) Microsoft. All rights reserved.

"""Bing Web Search tool using Azure Cognitive Services."""

import os
from typing import Annotated

from agent_framework import HostedWebSearchTool, ToolMode, ai_function
from pydantic import Field

from spec_to_agents.utils.clients import create_agent_client


@ai_function  # type: ignore[arg-type]
async def web_search(
    query: Annotated[str, Field(description="Search query to find information on the web")],
) -> str:
    """
    Search the web using Bing Search API and return formatted results.

    Parameters
    ----------
    query : str
        The search query string

    Returns
    -------
    str
        Formatted search results with titles, snippets, and URLs, or error message

    Notes
    -----
    Results are formatted for language model consumption with clear structure:
    - Result count at top
    - Numbered results
    - Title, snippet, URL, and display URL for each result

    Uses a temporary agent with auto-cleanup via async context manager.
    """
    # Ensure conflicting environment variables are not set
    os.environ.pop("BING_CUSTOM_CONNECTION_NAME", None)
    os.environ.pop("BING_CUSTOM_INSTANCE_NAME", None)
    try:
        web_search_tool = HostedWebSearchTool(description="Search the web for current information using Bing")

        # Use async context manager for proper cleanup
        async with create_agent_client() as client:
            agent = client.create_agent(
                name="bing_web_search_agent",
                tools=[web_search_tool],
                system_message=(
                    "You are a web search agent that uses the Bing Web Search tool to find information on the web."
                ),
                tool_choice=ToolMode.REQUIRED(function_name="web_search"),
                store=True,
                model_id=os.getenv("WEB_SEARCH_MODEL", "gpt-4.1-mini"),
            )
            response = await agent.run(f"Perform a web search for: {query}")
            return response.text
        # Agent automatically cleaned up when context manager exits

    except Exception as e:
        # Handle API errors gracefully
        error_type = type(e).__name__
        return f"Error performing web search: {error_type} - {e!s}"


__all__ = ["web_search"]
