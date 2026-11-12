# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_053():
    # <doc_manage_hosted_agent_list_all_agents_in_a_project>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        for agent in project_client.agents.list():
            print(agent.name)
    # </doc_manage_hosted_agent_list_all_agents_in_a_project>


def main():
    examples = {"aip-python-053": example_053}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-053")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
