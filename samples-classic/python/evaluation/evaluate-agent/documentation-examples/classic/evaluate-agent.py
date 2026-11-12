# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_018():
    # <doc_agent_evaluate_sdk_create_agent_threads_and_runs>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        from azure.ai.agents.models import FunctionTool, ToolSet
        from typing import Set, Callable, Any
        import json

        def fetch_weather(location: str) -> str:
            """
            Fetches the weather information for the specified location.

            :param location (str): The location to fetch weather for.
            :return: Weather information as a JSON string.
            :rtype: str
            """
            mock_weather_data = {
                "Seattle": "Sunny, 25°C",
                "London": "Cloudy, 18°C",
                "Tokyo": "Rainy, 22°C",
            }
            weather = mock_weather_data.get(
                location, "Weather data not available for this location."
            )
            weather_json = json.dumps({"weather": weather})
            return weather_json

        user_functions: Set[Callable[..., Any]] = {fetch_weather}
        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)
        AGENT_NAME = "Seattle Tourist Assistant"
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=project_endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = project_client.agents.create_agent(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            name="my-agent",
            instructions="You are a helpful agent",
            toolset=toolset,
        )
        print(f"Created agent, ID: {agent.id}")
        thread = project_client.agents.threads.create()
        print(f"Created thread, ID: {thread.id}")
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="What is the weather in Seattle today?",
        )
        print(f"Created message, ID: {message.id}")
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )
        print(f"Run finished with status: {run.status}")
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
        messages = project_client.agents.messages.list(thread_id=thread.id)
        for message in messages:
            print(f"Role: {message.role}, Content: {message.content}")
    # </doc_agent_evaluate_sdk_create_agent_threads_and_runs>


def main():
    examples = {"aip-python-018": example_018}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-018")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
