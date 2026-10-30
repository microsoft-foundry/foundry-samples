# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_165():
    # <doc_quickstart_evaluate_hosted_agent_step_1_confirm_your_deployed_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment = os.environ["FOUNDRY_MODEL_NAME"]
        credential = _resources.enter_context(DefaultAzureCredential())
        project_client = _resources.enter_context(
            AIProjectClient(endpoint=endpoint, credential=credential)
        )
        client = _resources.enter_context(project_client.get_openai_client())
    # </doc_quickstart_evaluate_hosted_agent_step_1_confirm_your_deployed_agent>


def main():
    examples = {"aip-python-165": example_165}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-165")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
