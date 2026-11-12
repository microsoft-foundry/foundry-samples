# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_161():
    # <doc_evaluation_dataset_synthetic_generate_a_dataset_from_an_agent_definition_sdk>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        credential = _resources.enter_context(DefaultAzureCredential())
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
            )
        )
    # </doc_evaluation_dataset_synthetic_generate_a_dataset_from_an_agent_definition_sdk>


def main():
    examples = {"aip-python-161": example_161, "aip-python-164": example_161}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-161")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
