# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_019():
    # <doc_cloud_evaluation_get_started>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
    # </doc_cloud_evaluation_get_started>


def main():
    examples = {"aip-python-019": example_019}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-019")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
