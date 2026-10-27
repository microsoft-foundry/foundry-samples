# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_081():
    # <doc_computer_use_prompt_agents>
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition, ComputerUsePreviewTool
    from computer_use_util import (
        SearchState,
        load_screenshot_assets,
        handle_computer_action_and_take_screenshot,
        print_final_output,
    )

    "Main function to demonstrate Computer Use Agent functionality."
    current_state = SearchState.INITIAL
    try:
        screenshots = load_screenshot_assets()
        print("Successfully loaded screenshot assets")
    except FileNotFoundError:
        print(
            "Failed to load required screenshot assets. Use the maintained SDK sample on GitHub to get the helper file and images."
        )
        exit(1)
    # </doc_computer_use_prompt_agents>


def example_082():
    # <doc_computer_use_create_an_agent_version_with_the_tool>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            ComputerUsePreviewTool,
        )
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            ComputerUsePreviewTool,
        )
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        computer_use_tool = ComputerUsePreviewTool(
            display_width=1026, display_height=769, environment="windows"
        )
        agent = project.agents.create_version(
            agent_name="ComputerUseAgent",
            definition=PromptAgentDefinition(
                model="computer-use-preview",
                instructions="\n        You are a computer automation assistant. \n\n        Be direct and efficient. When you reach the search results page, read and describe the actual search result titles and descriptions you can see.\n        ",
                tools=[computer_use_tool],
            ),
            description="Computer automation agent with screen interaction capabilities.",
        )
        print(f"Agent created (id: {agent.id}, name: {agent.name})")
    # </doc_computer_use_create_an_agent_version_with_the_tool>


def main():
    examples = {"aip-python-081": example_081, "aip-python-082": example_082}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-081")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
