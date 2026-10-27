# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_026():
    # <doc_copilot_sdk_build_rag_verify_your_setup>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        from azure.ai.projects import AIProjectClient
        import os
        from azure.identity import DefaultAzureCredential
        import azure.ai.projects

        print(f"Azure AI Projects SDK version: {azure.ai.projects.__version__}")
        project = _resources.enter_context(
            AIProjectClient.from_connection_string(
                conn_str=os.environ["FOUNDRY_PROJECT_CONNECTION_STRING"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        print("Project client initialized locally; authentication has not been tested.")
    # </doc_copilot_sdk_build_rag_verify_your_setup>


def example_028():
    # <doc_copilot_sdk_evaluate_verify_your_evaluation_setup>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project = _resources.enter_context(
            AIProjectClient.from_connection_string(
                conn_str=os.environ["FOUNDRY_PROJECT_CONNECTION_STRING"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        print("Project client initialized locally; no evaluation has been run.")
    # </doc_copilot_sdk_evaluate_verify_your_evaluation_setup>


def main():
    examples = {
        "aip-python-026": example_026,
        "aip-python-027": example_026,
        "aip-python-028": example_028,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-026")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
