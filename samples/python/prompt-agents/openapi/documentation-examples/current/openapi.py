# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_099():
    # <doc_openapi_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        from azure.ai.projects.models import OpenApiAnonymousAuthDetails
        import os
        import jsonref
        from typing import Any, cast
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            OpenApiTool,
            OpenApiFunctionDefinition,
            OpenApiProjectConnectionAuthDetails,
            OpenApiProjectConnectionSecurityScheme,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            weather_asset_file_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "assets/weather_openapi.json")
            )
            with open(weather_asset_file_path, "r") as f:
                openapi_weather = cast(dict[str, Any], jsonref.loads(f.read()))
            weather_tool = OpenApiTool(
                openapi=OpenApiFunctionDefinition(
                    name="get_weather",
                    spec=openapi_weather,
                    description="Retrieve weather information for a location.",
                    auth=OpenApiAnonymousAuthDetails(),
                )
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful assistant.",
                    tools=[weather_tool],
                ),
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                response = openai.responses.create(
                    input="What's the weather in Seattle?"
                )
                print(response.output_text)
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
    # </doc_openapi_prompt_agents>


def main():
    examples = {"aip-python-099": example_099}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-099")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
