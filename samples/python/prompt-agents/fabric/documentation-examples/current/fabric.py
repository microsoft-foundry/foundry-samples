# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_090():
    # <doc_fabric_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            MicrosoftFabricPreviewTool,
            FabricDataAgentToolParameters,
            ToolProjectConnection,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        FABRIC_CONNECTION_NAME = "my-fabric-connection"
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        fabric_connection = project.connections.get(FABRIC_CONNECTION_NAME)
        agent = project.agents.create_version(
            agent_name="MyAgent",
            definition=PromptAgentDefinition(
                model="gpt-4.1-mini",
                instructions="You are a helpful assistant.",
                tools=[
                    MicrosoftFabricPreviewTool(
                        fabric_dataagent_preview=FabricDataAgentToolParameters(
                            project_connections=[
                                ToolProjectConnection(
                                    project_connection_id=fabric_connection.id
                                )
                            ]
                        )
                    )
                ],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=agent.name)
        )
        user_input = input(
            "Enter your question for Fabric (e.g., 'Tell me about sales records'): \n"
        )
        response = openai.responses.create(tool_choice="required", input=user_input)
        print(f"Response output: {response.output_text}")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        print("Agent deleted")
    # </doc_fabric_prompt_agents>


def main():
    examples = {"aip-python-090": example_090}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-090")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
