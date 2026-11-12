# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_087():
    # <doc_fabric_iq_prompt_agents>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition, FabricIQPreviewTool

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    AGENT_NAME = "MyAgent"
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        tool_payload = FabricIQPreviewTool(
            project_connection_id=os.environ["FOUNDRY_FABRIC_IQ_PROJECT_CONNECTION_ID"],
            require_approval="never",
        )
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                instructions="Use the available Fabric IQ tools to answer questions and perform tasks.",
                tools=[tool_payload],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        with project.get_openai_client(agent_name=agent.name) as openai:
            user_input = "Which customers placed orders above $10,000 last quarter?"
            response = openai.responses.create(input=user_input)
            print(f"Agent response: {response.output_text}")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        print("Agent deleted")
    # </doc_fabric_iq_prompt_agents>


def main():
    examples = {"aip-python-087": example_087}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-087")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
