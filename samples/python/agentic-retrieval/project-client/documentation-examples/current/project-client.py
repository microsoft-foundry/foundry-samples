# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_170():
    # <doc_agentic_retrieval_how_to_create_pipeline_set_up_a_project_client>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        from azure.identity import DefaultAzureCredential

        project_endpoint = PROJECT_ENDPOINT
        credential = _resources.enter_context(DefaultAzureCredential())
        from azure.ai.projects import AIProjectClient

        project_client = _resources.enter_context(
            AIProjectClient(endpoint=project_endpoint, credential=credential)
        )
        agents = list(project_client.agents.list())
        print(f"Found {len(agents)} agents")
        for agent in agents:
            print(agent.name)
    # </doc_agentic_retrieval_how_to_create_pipeline_set_up_a_project_client>


def main():
    examples = {"aip-python-170": example_170}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-170")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
