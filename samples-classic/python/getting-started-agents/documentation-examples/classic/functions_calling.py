# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_012():
    # <doc_function_calling_function_calling_code_example>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os, time
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.agents.models import FunctionTool
        import json
        import datetime
        from typing import Any, Callable, Set, Dict, List, Optional

        def fetch_weather(location: str) -> str:
            """
            Fetches the weather information for the specified location.

            :param location: The location to fetch weather for.
            :return: Weather information as a JSON string.
            """
            mock_weather_data = {
                "New York": "Sunny, 25°C",
                "London": "Cloudy, 18°C",
                "Tokyo": "Rainy, 22°C",
            }
            weather = mock_weather_data.get(
                location, "Weather data not available for this location."
            )
            return json.dumps({"weather": weather})

        user_functions = {fetch_weather}
        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_name = os.environ["FOUNDRY_MODEL_NAME"]
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=project_endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        functions = FunctionTool(functions=user_functions)
        with project_client:
            agent = project_client.agents.create_agent(
                model=model_name,
                name="my-agent",
                instructions="You are a helpful agent",
                tools=functions.definitions,
            )
            print(f"Created agent, ID: {agent.id}")
        thread = project_client.agents.threads.create()
        print(f"Created thread, ID: {thread.id}")
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Hello, send an email with the datetime and weather information in New York?",
        )
        print(f"Created message, ID: {message['id']}")
        run = project_client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
        print(f"Created run, ID: {run.id}")
        while run.status in ["queued", "in_progress", "requires_action"]:
            time.sleep(1)
            run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                for tool_call in tool_calls:
                    if tool_call.function.name == "fetch_weather":
                        output = fetch_weather("New York")
                        tool_outputs.append(
                            {"tool_call_id": tool_call.id, "output": output}
                        )
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )
        print(f"Run completed with status: {run.status}")
        messages = project_client.agents.messages.list(thread_id=thread.id)
        for message in messages:
            print(f"Role: {message['role']}, Content: {message['content']}")
        project_client.agents.delete_agent(agent.id)
        print("Deleted agent")
    # </doc_function_calling_function_calling_code_example>


def main():
    examples = {"aip-python-012": example_012}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-012")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
