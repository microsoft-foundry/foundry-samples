# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_119():
    # <doc_work_iq_prompt_agents>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition, WorkIQPreviewTool

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    AGENT_NAME = "MyAgent"
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        tool_payload = WorkIQPreviewTool(
            project_connection_id=os.environ["FOUNDRY_WORK_IQ_PROJECT_CONNECTION_ID"]
        )
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="Use the available WorkIQ tools to answer questions and perform tasks.",
                tools=[tool_payload],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        with project.get_openai_client(agent_name=agent.name) as openai:
            user_input = "Summarize my recent emails about Project Contoso."
            response = openai.responses.create(input=user_input)
            print(f"Agent response: {response.output_text}")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        print("Agent deleted")
    # </doc_work_iq_prompt_agents>


def main():
    examples = {"aip-python-119": example_119}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-119")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
