# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_039():
    # <doc_runtime_components_run_an_agent_in_background_mode>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from time import sleep
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = os.environ["FOUNDRY_AGENT_NAME"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        response = openai.responses.create(
            input="Write a detailed analysis of renewable energy trends.",
            background=True,
        )
        while response.status in ("queued", "in_progress"):
            sleep(2)
            response = openai.responses.retrieve(response.id)
        print(response.output_text)
    # </doc_runtime_components_run_an_agent_in_background_mode>


def example_098():
    # <doc_model_context_protocol_run_background_mode_with_code>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from time import sleep
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = os.environ["FOUNDRY_MCP_AGENT_NAME"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        response = openai.responses.create(
            input="Run the long-running task and summarize the result.", background=True
        )
        while response.status in ("queued", "in_progress"):
            sleep(5)
            response = openai.responses.retrieve(response.id)
        print(response.output_text)
    # </doc_model_context_protocol_run_background_mode_with_code>


def main():
    examples = {"aip-python-039": example_039, "aip-python-098": example_098}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-039")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
