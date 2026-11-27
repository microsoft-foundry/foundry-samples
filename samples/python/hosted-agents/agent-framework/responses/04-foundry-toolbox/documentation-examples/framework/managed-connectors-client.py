# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_084():
    # <doc_connectors_step_7_use_the_connection_from_your_agent>
    import os

    CONNECTION_NAME = os.environ["FOUNDRY_CONNECTOR_CONNECTION_NAME"]
    SERVER_URL = os.environ["FOUNDRY_CONNECTOR_MCP_URL"]
    import asyncio
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, MCPToolboxTool

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            toolbox = project.toolboxes.create_version(
                name="connector-toolbox",
                description="Toolbox with the connector MCP server",
                tools=[
                    MCPToolboxTool(
                        server_label=CONNECTION_NAME,
                        server_url=SERVER_URL,
                        project_connection_id=CONNECTION_NAME,
                        require_approval="never",
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
                    instructions="You are an assistant that uses connector actions to complete tasks.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "Use the connector actions to summarize the latest items that need my attention."
            )
            print(result.text)

    asyncio.run(main())
    # </doc_connectors_step_7_use_the_connection_from_your_agent>


def main():
    examples = {"aip-python-084": example_084}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-084")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
