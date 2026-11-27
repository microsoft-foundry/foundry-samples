# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_080():
    # <doc_code_interpreter_hosted_agents>
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        CodeInterpreterToolboxTool,
        AutoCodeInterpreterToolParam,
    )

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    CSV_DATA = "name,sector,operating_profit\nSkyBridge Logistics,TRANSPORTATION,185.2\nVelocity Rail Freight,TRANSPORTATION,310.2\nAeroJet Airlines,TRANSPORTATION,510.6\n"

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            csv_path = os.path.abspath("synthetic-company-financial-results.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as csv_file:
                csv_file.write(CSV_DATA)
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            openai = _resources.enter_context(project.get_openai_client())
            with open(csv_path, "rb") as csv_file:
                file = openai.files.create(purpose="assistants", file=csv_file)
            os.remove(csv_path)
            toolbox = project.toolboxes.create_version(
                name="code-interpreter-toolbox",
                description="Toolbox with the code interpreter tool",
                tools=[
                    CodeInterpreterToolboxTool(
                        container=AutoCodeInterpreterToolParam(file_ids=[file.id])
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
                    instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run("Use code to calculate the factorial of 100.")
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_code_interpreter_hosted_agents>


def main():
    examples = {"aip-python-080": example_080}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-080")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
