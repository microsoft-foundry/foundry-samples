# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_038():
    # <doc_runtime_components_stream_a_response>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
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
        stream = openai.responses.create(
            input="Explain how agents work in one paragraph.", stream=True
        )
        for event in stream:
            if hasattr(event, "delta") and event.delta:
                print(event.delta, end="", flush=True)
    # </doc_runtime_components_stream_a_response>


def main():
    examples = {"aip-python-038": example_038}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-038")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
