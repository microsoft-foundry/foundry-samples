# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_086():
    # <doc_custom_code_interpreter_use_a_hosted_agent>
    import os
    import asyncio
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPToolboxTool

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    MCP_SERVER_URL = os.environ["FOUNDRY_MCP_SERVER_URL"]
    MCP_CONNECTION_ID = os.environ["FOUNDRY_MCP_CONNECTION_ID"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            toolbox = project.toolboxes.create_version(
                name="custom-code-interpreter-toolbox",
                description="Toolbox with the custom code interpreter MCP server",
                tools=[
                    MCPToolboxTool(
                        server_label="custom-code-interpreter",
                        server_url=MCP_SERVER_URL,
                        project_connection_id=MCP_CONNECTION_ID,
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
                    instructions="You are a helpful assistant that can run Python code to analyze data and solve problems.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run("Calculate the factorial of 10 using Python.")
            print(result.text)
            project.toolboxes.delete_version(name=toolbox.name, version=toolbox.version)

    asyncio.run(main())
    # </doc_custom_code_interpreter_use_a_hosted_agent>


def main():
    examples = {"aip-python-086": example_086}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-086")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
