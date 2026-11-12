# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_051():
    # <doc_enable_agent_to_agent_endpoint_step_2_create_the_calling_agent_with_the_a2a_tool>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            A2AProtocolVersion,
            A2ATool,
            PromptAgentDefinition,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        A2A_CONNECTION_NAME = "my-a2a-target"
        AGENT_NAME = "my-calling-agent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            a2a_connection = project.connections.get(A2A_CONNECTION_NAME)
            tool = A2ATool(
                a2a_version=A2AProtocolVersion.V1_0,
                project_connection_id=a2a_connection.id,
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful assistant. Use the A2A tool to delegate tasks to the target agent.",
                    tools=[tool],
                ),
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                stream_response = openai.responses.create(
                    stream=True, input="Ask the target agent what it can do."
                )
                for event in stream_response:
                    if event.type == "response.output_text.delta":
                        print(event.delta, end="")
                    elif event.type == "response.completed":
                        print(f"\n\nCompleted: {event.response.output_text}")
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
    # </doc_enable_agent_to_agent_endpoint_step_2_create_the_calling_agent_with_the_a2a_tool>


def example_068():
    # <doc_agent_to_agent_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            A2AProtocolVersion,
            A2ATool,
            PromptAgentDefinition,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        A2A_CONNECTION_NAME = "my-a2a-connection"
        AGENT_NAME = "my-agent"
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        a2a_connection = project.connections.get(A2A_CONNECTION_NAME)
        tool = A2ATool(
            a2a_version=A2AProtocolVersion.V1_0, project_connection_id=a2a_connection.id
        )
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful assistant.",
                tools=[tool],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
    # </doc_agent_to_agent_prompt_agents>


def main():
    examples = {"aip-python-051": example_051, "aip-python-068": example_068}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-051")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
