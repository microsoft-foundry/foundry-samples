# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_005():
    # <doc_bing_code_samples_create_a_project_client>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents.models import BingGroundingTool

        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=project_endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
    # </doc_bing_code_samples_create_a_project_client>


def main():
    examples = {"aip-python-005": example_005}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-005")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
