# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_116():
    # <doc_web_search_create_a_toolbox_and_run_a_hosted_agent>
    import os
    import asyncio
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        WebSearchToolboxTool,
        WebSearchApproximateLocation,
    )

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            toolbox = project.toolboxes.create_version(
                name="web-search-toolbox",
                description="Toolbox with the web search tool",
                tools=[
                    WebSearchToolboxTool(
                        user_location=WebSearchApproximateLocation(
                            country="GB", city="London", region="London"
                        )
                    )
                ],
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
                    instructions="You are a research assistant. Use web search to find current information.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "What are the latest updates to Microsoft Foundry?"
            )
            print(f"Agent: {result.text}")
            for message in result.messages:
                for content in message.contents:
                    for annotation in getattr(content, "annotations", None) or []:
                        url = getattr(annotation, "url", None)
                        if url:
                            title = getattr(annotation, "title", None) or ""
                            print(f"URL Citation: [{title}]({url})")

    asyncio.run(main())
    # </doc_web_search_create_a_toolbox_and_run_a_hosted_agent>


def main():
    examples = {"aip-python-116": example_116}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-116")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
