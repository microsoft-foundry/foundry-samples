# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_093():
    # <doc_file_search_hosted_agents>
    import os
    import asyncio
    from pathlib import Path
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import FileSearchToolboxTool
    from azure.identity import AzureCliCredential

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            asset_file_path = (
                Path(__file__).parent / "assets/product_info.md"
            ).resolve()
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            openai = _resources.enter_context(project.get_openai_client())
            vector_store = openai.vector_stores.create(name="ProductInfoStore")
            with asset_file_path.open("rb") as file_handle:
                vector_store_file = openai.vector_stores.files.upload_and_poll(
                    vector_store_id=vector_store.id, file=file_handle
                )
            toolbox = project.toolboxes.create_version(
                name="file-search-toolbox",
                description="Toolbox with the file search tool",
                tools=[FileSearchToolboxTool(vector_store_ids=[vector_store.id])],
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
                    instructions="You are a helpful assistant that can search through files to find information.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "What is the weather today? Do a file search to find the answer."
            )
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_file_search_hosted_agents>


def main():
    examples = {"aip-python-093": example_093}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-093")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
