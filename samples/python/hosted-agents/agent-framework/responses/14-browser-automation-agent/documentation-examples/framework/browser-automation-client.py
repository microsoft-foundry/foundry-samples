# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_078():
    # <doc_browser_automation_hosted_agents>
    import os
    import asyncio
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        BrowserAutomationToolParameters,
        BrowserAutomationToolConnectionParameters,
    )
    from azure.identity import AzureCliCredential

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    BROWSER_CONNECTION_ID = os.environ["FOUNDRY_BROWSER_CONNECTION_ID"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            tool = {
                "type": "browser_automation",
                "browser_automation": BrowserAutomationToolParameters(
                    connection=BrowserAutomationToolConnectionParameters(
                        project_connection_id=BROWSER_CONNECTION_ID
                    )
                ).as_dict(),
            }
            toolbox = project.toolboxes.create_version(
                name="browser-automation-toolbox",
                body={
                    "description": "Toolbox with the Browser Automation tool",
                    "tools": [tool],
                },
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
                    instructions="You help with browser automation tasks. Use the Browser Automation tool to navigate and read information from websites.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run(
                "Go to finance.yahoo.com, search for MSFT, click 'YTD' on the price chart, and report the year-to-date percent change."
            )
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_browser_automation_hosted_agents>


def main():
    examples = {"aip-python-078": example_078}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-078")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
