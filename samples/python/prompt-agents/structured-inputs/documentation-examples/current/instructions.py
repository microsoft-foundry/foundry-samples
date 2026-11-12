# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_061():
    # <doc_structured_inputs_use_structured_inputs_with_agent_instructions>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            StructuredInputDefinition,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "structured-input-agent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="You are a helpful assistant. The user's name is {{userName}} and their role is {{userRole}}. Greet them and confirm their details.",
                    structured_inputs={
                        "userName": StructuredInputDefinition(
                            description="The user's name",
                            required=True,
                            schema={"type": "string"},
                        ),
                        "userRole": StructuredInputDefinition(
                            description="The user's role",
                            required=True,
                            schema={"type": "string"},
                        ),
                    },
                ),
            )
            print(f"Agent created: {agent.name}, version: {agent.version}")
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                response = openai.responses.create(
                    conversation=conversation.id,
                    input="Hello! Can you confirm my details?",
                    extra_body={
                        "structured_inputs": {
                            "userName": "Alice Smith",
                            "userRole": "Senior Developer",
                        }
                    },
                )
                print(response.output_text)
    # </doc_structured_inputs_use_structured_inputs_with_agent_instructions>


def main():
    examples = {"aip-python-061": example_061}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-061")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
