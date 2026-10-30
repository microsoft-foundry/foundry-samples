# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_152():
    # <doc_how_to_high_availability_resiliency_1_back_up_agent_definitions>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import json
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as client:
            agents = client.agents.list()
            for agent in agents:
                with open(f"{agent.id}.json", "w") as f:
                    json.dump(dict(agent), f, indent=2)
                print(f"Saved agent: {agent.name} ({agent.id})")
    # </doc_how_to_high_availability_resiliency_1_back_up_agent_definitions>


def main():
    examples = {"aip-python-152": example_152}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-152")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
