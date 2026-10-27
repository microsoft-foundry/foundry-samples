# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_100():
    # <doc_openapi_hosted_agents>
    import asyncio
    import os
    import jsonref
    from typing import Any, cast
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, FoundryToolbox
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        OpenApiToolboxTool,
        OpenApiFunctionDefinition,
        OpenApiProjectConnectionAuthDetails,
        OpenApiProjectConnectionSecurityScheme,
    )

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    async def main() -> None:
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as _resources:
            credential = _resources.enter_context(AzureCliCredential())
            project = _resources.enter_context(
                AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
            )
            weather_asset_file_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "assets/weather_openapi.json")
            )
            with open(weather_asset_file_path, encoding="utf-8") as f:
                openapi_weather = cast(dict[str, Any], jsonref.loads(f.read()))
            weather_tool = OpenApiToolboxTool(
                openapi=OpenApiFunctionDefinition(
                    name="get_weather",
                    spec=openapi_weather,
                    description="Retrieve weather information for a location.",
                    auth=OpenApiProjectConnectionAuthDetails(
                        security_scheme=OpenApiProjectConnectionSecurityScheme(
                            project_connection_id=os.environ[
                                "FOUNDRY_OPENAPI_CONNECTION_ID"
                            ]
                        )
                    ),
                )
            )
            toolbox = project.toolboxes.create_version(
                name="openapi-toolbox",
                description="Toolbox with the OpenAPI weather tool",
                tools=[weather_tool],
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
                    instructions="You are a helpful assistant. Use the OpenAPI weather tool to answer questions.",
                    tools=[toolbox_tool],
                )
            )
            result = await agent.run("What's the weather in Seattle?")
            print(f"Agent: {result.text}")

    asyncio.run(main())
    # </doc_openapi_hosted_agents>


def main():
    examples = {"aip-python-100": example_100}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-100")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
