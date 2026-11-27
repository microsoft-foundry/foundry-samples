# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_033():
    # <doc_runtime_components_generate_a_response_with_an_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = os.environ["FOUNDRY_AGENT_NAME"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        response = openai.responses.create(input="What is the largest city in France?")
        print(response.output_text)
        follow_up = openai.responses.create(
            previous_response_id=response.id,
            input="What is the population of that city?",
        )
        print(follow_up.output_text)
    # </doc_runtime_components_generate_a_response_with_an_agent>


def example_037():
    # <doc_runtime_components_use_a_conversation_with_an_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = os.environ["FOUNDRY_AGENT_NAME"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id, input="What is the largest city in France?"
        )
        print(response.output_text)
        follow_up = openai.responses.create(
            conversation=conversation.id, input="What is the population of that city?"
        )
        print(follow_up.output_text)
    # </doc_runtime_components_use_a_conversation_with_an_agent>


def main():
    examples = {"aip-python-033": example_033, "aip-python-037": example_037}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-033")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
