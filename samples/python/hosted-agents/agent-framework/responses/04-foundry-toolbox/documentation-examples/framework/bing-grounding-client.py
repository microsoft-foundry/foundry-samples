# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_075():
    # <doc_bing_tools_hosted_agents>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    BING_CONNECTION_NAME = "my-bing-connection"

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
            connection_id = project.connections.get(BING_CONNECTION_NAME).id
            agent = await _resources.enter_async_context(
                Agent(
                    client=FoundryChatClient(
                        credential=credential,
                        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                        model=os.environ["FOUNDRY_MODEL_NAME"],
                    ),
                    instructions="You are a helpful assistant that can search the web with Bing.",
                    tools=[
                        FoundryChatClient.get_bing_grounding_tool(
                            connection_id=connection_id,
                            market="en-US",
                            count=10,
                            freshness="Day",
                        )
                    ],
                )
            )
            result = await agent.run("What is today's date and weather in Seattle?")
            print(f"Agent: {result.text}")
            for message in result.messages:
                for content in message.contents:
                    for annotation in getattr(content, "annotations", None) or []:
                        url = getattr(annotation, "url", None)
                        if url:
                            print(f"URL Citation: {url}")

    asyncio.run(main())
    # </doc_bing_tools_hosted_agents>


def main():
    examples = {"aip-python-075": example_075}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-075")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
