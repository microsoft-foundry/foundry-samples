# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_132():
    # <doc_prompt_voice_agent_clean_up_resources>
    import os
    import sys
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    conversation_id = sys.argv[1]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        project_client.beta.voice_agents.conversations.delete(
            agent_name, conversation_id
        )
        project_client.agents.delete(agent_name=agent_name)
    # </doc_prompt_voice_agent_clean_up_resources>


def main():
    examples = {"aip-python-132": example_132}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-132")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    argument_examples = {"aip-python-132"}
    arguments = options.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if arguments and options.example not in argument_examples:
        parser.error("This example does not accept additional arguments.")
    original_arguments = sys.argv
    sys.argv = [sys.argv[0], *arguments]
    try:
        examples[options.example]()
    finally:
        sys.argv = original_arguments
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
