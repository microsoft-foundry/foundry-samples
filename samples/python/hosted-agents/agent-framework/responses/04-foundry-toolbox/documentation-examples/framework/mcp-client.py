# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_097():
    # <doc_model_context_protocol_hosted_agents>
    import os
    import asyncio
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPToolboxTool
    from azure.identity import AzureCliCredential

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    MCP_CONNECTION_NAME = "my-mcp-connection"

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            server_tool = MCPToolboxTool(
                server_label="api-specs",
                server_url="https://api.githubcopilot.com/mcp",
                require_approval="always",
                project_connection_id=MCP_CONNECTION_NAME,
            )
            toolbox = project.toolboxes.create_version(
                name="mcp-server-toolbox",
                description="Toolbox with the GitHub MCP server",
                tools=[server_tool],
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
                    instructions="You are a helpful assistant that uses your MCP tool to help with Microsoft documentation questions.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run("What is Microsoft Agent Framework?")
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_model_context_protocol_hosted_agents>


def main():
    examples = {"aip-python-097": example_097}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-097")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
