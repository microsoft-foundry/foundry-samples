# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_003():
    # <doc_azure_functions_samples_configure_the_azure_function_tool>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool

    storage_service_endpoint = os.environ["FOUNDRY_STORAGE_SERVICE_ENDPOINT"]
    azure_function_tool = AzureFunctionTool(
        name="foo",
        description="Get answers from the foo bot.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question to ask."},
                "outputqueueuri": {
                    "type": "string",
                    "description": "The full output queue URI.",
                },
            },
        },
        input_queue=AzureFunctionStorageQueue(
            queue_name="azure-function-foo-input",
            storage_service_endpoint=storage_service_endpoint,
        ),
        output_queue=AzureFunctionStorageQueue(
            queue_name="azure-function-foo-output",
            storage_service_endpoint=storage_service_endpoint,
        ),
    )
    # </doc_azure_functions_samples_configure_the_azure_function_tool>


def example_004():
    # <doc_azure_functions_samples_create_an_ai_project_client_and_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool

        storage_service_endpoint = os.environ["FOUNDRY_STORAGE_SERVICE_ENDPOINT"]
        azure_function_tool = AzureFunctionTool(
            name="foo",
            description="Get answers from the foo bot.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The question to ask."},
                    "outputqueueuri": {
                        "type": "string",
                        "description": "The full output queue URI.",
                    },
                },
            },
            input_queue=AzureFunctionStorageQueue(
                queue_name="azure-function-foo-input",
                storage_service_endpoint=storage_service_endpoint,
            ),
            output_queue=AzureFunctionStorageQueue(
                queue_name="azure-function-foo-output",
                storage_service_endpoint=storage_service_endpoint,
            ),
        )
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = project_client.agents.create_agent(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            name="azure-function-agent-foo",
            instructions=f"""You are a helpful support agent. Use the provided function any time the prompt contains the string 'What would foo say?'. When you invoke the function, ALWAYS specify the output queue URI parameter as '{storage_service_endpoint}/azure-function-tool-output'. Always respond with "Foo says" and then the response from the tool.""",
            tools=azure_function_tool.definitions,
        )
        print(f"Created agent, agent ID: {agent.id}")
    # </doc_azure_functions_samples_create_an_ai_project_client_and_agent>


def main():
    examples = {"aip-python-003": example_003, "aip-python-004": example_004}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-003")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
