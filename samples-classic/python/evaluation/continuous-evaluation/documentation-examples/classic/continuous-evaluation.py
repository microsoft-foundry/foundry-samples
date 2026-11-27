# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_017():
    # <doc_continuous_evaluation_agents_create_agent_run>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.agents.models import FileSearchTool

        file_search_tool = FileSearchTool(
            vector_store_ids=[os.environ["FOUNDRY_VECTOR_STORE_ID"]]
        )
        import os, json
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project_client = _resources.enter_context(
            AIProjectClient(
                credential=_resources.enter_context(DefaultAzureCredential()),
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            )
        )
        agent = project_client.agents.create_agent(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            name="my-assistant",
            instructions="You are a helpful assistant",
            tools=file_search_tool.definitions,
            tool_resources=file_search_tool.resources,
        )
        thread = project_client.agents.threads.create()
        project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Hello, what Contoso products do you know?",
        )
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
        for message in project_client.agents.messages.list(thread_id=thread.id):
            for text_message in message.text_messages:
                print(text_message.text.value)
    # </doc_continuous_evaluation_agents_create_agent_run>


def main():
    examples = {"aip-python-017": example_017}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-017")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
