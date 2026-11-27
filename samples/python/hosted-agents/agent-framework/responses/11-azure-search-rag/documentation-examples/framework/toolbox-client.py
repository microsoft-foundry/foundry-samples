# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_071():
    # <doc_ai_search_expected_outcome>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AISearchIndexResource,
        AzureAISearchQueryType,
        AzureAISearchTool,
        AzureAISearchToolResource,
    )
    from azure.identity import AzureCliCredential

    SEARCH_CONNECTION_NAME = "my-search-connection"
    SEARCH_INDEX_NAME = "my-search-index"

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            azs_connection = project.connections.get(SEARCH_CONNECTION_NAME)
            connection_id = azs_connection.id
            ai_search_tool = AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=connection_id,
                            index_name=SEARCH_INDEX_NAME,
                            query_type=AzureAISearchQueryType.SIMPLE,
                        )
                    ]
                )
            )
            toolbox = project.toolboxes.create_version(
                name="ai-search-toolbox",
                description="Toolbox with the Azure AI Search tool",
                tools=[ai_search_tool],
            )
            TOOLBOX_MCP_URL = f"{PROJECT_ENDPOINT}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
            toolbox_tool = FoundryToolbox(credential, url=TOOLBOX_MCP_URL)
            agent = await _resources.enter_async_context(
                Agent(
                    client=FoundryChatClient(
                        credential=credential,
                        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                        model=os.environ["FOUNDRY_MODEL_NAME"],
                    ),
                    instructions="You are a helpful assistant. Always cite sources from the search index using `[message_idx:search_idx†source]`.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "Tell me about the mental health services available from Premera."
            )
            print(f"Agent: {result.text}")
            for message in result.messages:
                for content in message.contents:
                    for annotation in getattr(content, "annotations", None) or []:
                        url = getattr(annotation, "url", None)
                        title = getattr(annotation, "title", None)
                        if url:
                            print(f"URL Citation: {title or ''} ({url})")

    asyncio.run(main())
    # </doc_ai_search_expected_outcome>


def main():
    examples = {"aip-python-071": example_071}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-071")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
