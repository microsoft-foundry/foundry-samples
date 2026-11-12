# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_088():
    # <doc_fabric_iq_hosted_agents>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import FabricIQPreviewToolboxTool

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project_client = _resources.enter_context(
                AIProjectClient(endpoint=endpoint, credential=credential)
            )
            fabric_iq_tool = FabricIQPreviewToolboxTool(
                project_connection_id=os.environ[
                    "FOUNDRY_FABRIC_IQ_PROJECT_CONNECTION_ID"
                ]
            )
            toolbox = project_client.toolboxes.create_version(
                name="fabric-iq-toolbox",
                description="Toolbox with the Fabric IQ tool",
                tools=[fabric_iq_tool],
            )
            TOOLBOX_MCP_URL = f"{endpoint}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
            toolbox_tool = FoundryToolbox(credential, url=TOOLBOX_MCP_URL)
            agent = await _resources.enter_async_context(
                Agent(
                    client=FoundryChatClient(
                        credential=credential,
                        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                        model=os.environ["FOUNDRY_MODEL_NAME"],
                    ),
                    instructions="Use the available Fabric IQ tools to answer questions and perform tasks.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "Which customers placed orders above $10,000 last quarter?"
            )
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_fabric_iq_hosted_agents>


def example_089():
    # <doc_fabric_iq_python>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import FabricIQPreviewToolboxTool

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            fabric_iq_tool = FabricIQPreviewToolboxTool(
                project_connection_id=os.environ[
                    "FOUNDRY_FABRIC_IQ_PROJECT_CONNECTION_ID"
                ],
                server_label=os.environ["FOUNDRY_FABRIC_IQ_SERVER_LABEL"],
                server_url=os.environ["FOUNDRY_FABRIC_IQ_SERVER_URL"],
            )
            toolbox = project.toolboxes.create_version(
                name="fabric-iq-toolbox",
                description="Toolbox with the Fabric IQ tool",
                tools=[fabric_iq_tool],
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
                    instructions="Use the available Fabric IQ tools to answer questions about business entities, relationships, and data.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "Which customers placed orders above $10,000 last quarter?"
            )
            print(result.text)

    asyncio.run(main())
    # </doc_fabric_iq_python>


def main():
    examples = {"aip-python-088": example_088, "aip-python-089": example_089}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-088")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
