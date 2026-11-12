# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_091():
    # <doc_fabric_hosted_agents>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    FABRIC_CONNECTION_NAME = "my-fabric-connection"

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(
                    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                    credential=credential,
                )
            )
            fabric_connection_id = project.connections.get(FABRIC_CONNECTION_NAME).id
            agent = await _resources.enter_async_context(
                Agent(
                    client=FoundryChatClient(
                        credential=credential,
                        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                        model=os.environ["FOUNDRY_MODEL_NAME"],
                    ),
                    instructions="You are a helpful assistant. Use Fabric to answer data questions.",
                    tools=[
                        FoundryChatClient.get_fabric_tool(
                            connection_id=fabric_connection_id
                        )
                    ],
                )
            )
            result = await agent.run("Tell me about sales records.")
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_fabric_hosted_agents>


def main():
    examples = {"aip-python-091": example_091}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-091")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
