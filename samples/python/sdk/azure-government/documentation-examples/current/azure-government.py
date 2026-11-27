# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_029():
    # <doc_azure_government_sdk_configuration_for_azure_government>
    import os
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = "MyAgent"
    scope = "https://ai.azure.us/.default"
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, credential_scopes=[scope]
        ) as project_client,
    ):
        api_key = get_bearer_token_provider(credential, scope)
        agent = project_client.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                instructions="You are a helpful assistant",
            ),
        )
        print(f"Agent created (name: {agent.name}, version: {agent.version})")
        with project_client.get_openai_client(
            api_key=api_key, agent_name=agent.name
        ) as openai_client:
            conversation = openai_client.conversations.create(
                items=[{"type": "message", "role": "user", "content": "Hello!"}]
            )
            response = openai_client.responses.create(conversation=conversation.id)
            print(f"Response: {response.output_text}")
            openai_client.conversations.delete(conversation_id=conversation.id)
        project_client.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
    # </doc_azure_government_sdk_configuration_for_azure_government>


def main():
    examples = {"aip-python-029": example_029}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-029")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
