# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_073():
    # <doc_azure_functions_define_the_tool_and_create_an_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AzureFunctionBinding,
            AzureFunctionDefinition,
            AzureFunctionStorageQueue,
            AzureFunctionDefinitionFunction,
            AzureFunctionTool,
            PromptAgentDefinition,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        STORAGE_QUEUE_ENDPOINT = os.environ["FOUNDRY_STORAGE_QUEUE_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        tool = AzureFunctionTool(
            azure_function=AzureFunctionDefinition(
                input_binding=AzureFunctionBinding(
                    storage_queue=AzureFunctionStorageQueue(
                        queue_name="get-weather-input-queue",
                        queue_service_endpoint=STORAGE_QUEUE_ENDPOINT,
                    )
                ),
                output_binding=AzureFunctionBinding(
                    storage_queue=AzureFunctionStorageQueue(
                        queue_name="get-weather-output-queue",
                        queue_service_endpoint=STORAGE_QUEUE_ENDPOINT,
                    )
                ),
                function=AzureFunctionDefinitionFunction(
                    name="GetWeather",
                    description="Get the weather in a location.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The location to look up.",
                            }
                        },
                    },
                ),
            )
        )
        agent = project.agents.create_version(
            agent_name="azure-function-agent-get-weather",
            definition=PromptAgentDefinition(
                model="gpt-5.1",
                instructions="You are a helpful support agent. Answer the user's questions to the best of your ability.",
                tools=[tool],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
    # </doc_azure_functions_define_the_tool_and_create_an_agent>


def main():
    examples = {"aip-python-073": example_073}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-073")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
