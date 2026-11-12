# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_163():
    # <doc_trace_agent_client_side_export_traces_to_azure_monitor>
    import os

    os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.identity import DefaultAzureCredential
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    AGENT_NAME = "MyAgent"
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        connection_string = (
            project.telemetry.get_application_insights_connection_string()
        )
        configure_azure_monitor(connection_string=connection_string)
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("agent-tracing-scenario"):
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model=os.environ["FOUNDRY_MODEL_NAME"],
                    instructions="You are a helpful assistant.",
                ),
            )
            print(f"Agent created (id: {agent.id}, name: {agent.name})")
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                response = openai.responses.create(
                    conversation=conversation.id,
                    input="What is the largest city in France?",
                )
                print(f"Response: {response.output_text}")
                openai.conversations.delete(conversation_id=conversation.id)
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
    # </doc_trace_agent_client_side_export_traces_to_azure_monitor>


def main():
    examples = {"aip-python-163": example_163}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-163")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
