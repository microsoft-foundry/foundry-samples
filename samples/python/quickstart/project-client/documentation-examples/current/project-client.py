# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_171():
    # <doc_agents_multi_language_code_syntax>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with AIProjectClient(
            endpoint=endpoint,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as client:
            print("Project client initialized locally; no service request was sent.")
    # </doc_agents_multi_language_code_syntax>


def main():
    examples = {"aip-python-171": example_171}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-171")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
