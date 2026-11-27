# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_022():
    # <doc_sdk_overview_using_the_foundry_sdk>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
    # </doc_sdk_overview_using_the_foundry_sdk>


def example_169():
    # <doc_how_to_codex_content_persistent_guidance_with_agents_md>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        with project_client:
            agents_client = project_client.agents
            agent = agents_client.create_agent(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                name="my-helpful-agent",
                instructions="You are a helpful agent that can answer questions.",
            )
            print(f"Created agent with ID: {agent.id}")
    # </doc_how_to_codex_content_persistent_guidance_with_agents_md>


def main():
    examples = {"aip-python-022": example_022, "aip-python-169": example_169}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-022")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
