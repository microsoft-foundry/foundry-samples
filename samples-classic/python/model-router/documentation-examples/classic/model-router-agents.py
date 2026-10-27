# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_166():
    # <doc_model_router_agents_tailor_model_subsets_per_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        research_agent = project.agents.create_agent(
            model="router-frontier",
            name="research-agent",
            instructions="You are a research assistant that synthesizes complex information.",
        )
        assistant_agent = project.agents.create_agent(
            model="router-balanced",
            name="assistant-agent",
            instructions="You are a helpful assistant.",
        )
        triage_agent = project.agents.create_agent(
            model="router-efficient",
            name="triage-agent",
            instructions="You classify incoming requests and route them to the right team.",
        )
    # </doc_model_router_agents_tailor_model_subsets_per_agent>


def example_167():
    # <doc_model_router_agents_configure_your_agent_to_use_model_router>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = project.agents.create_agent(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            name="my-agent",
            instructions="You are a helpful assistant.",
        )
    # </doc_model_router_agents_configure_your_agent_to_use_model_router>


def main():
    examples = {"aip-python-166": example_166, "aip-python-167": example_167}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-166")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
