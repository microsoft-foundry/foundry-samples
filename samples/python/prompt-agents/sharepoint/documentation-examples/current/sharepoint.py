# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_102():
    # <doc_sharepoint_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            SharepointPreviewTool,
            SharepointGroundingToolParameters,
            ToolProjectConnection,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        SHAREPOINT_CONNECTION_NAME = "my-sharepoint-connection"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            sharepoint_connection = project.connections.get(SHAREPOINT_CONNECTION_NAME)
            sharepoint_tool = SharepointPreviewTool(
                sharepoint_grounding_preview=SharepointGroundingToolParameters(
                    project_connections=[
                        ToolProjectConnection(
                            project_connection_id=sharepoint_connection.id
                        )
                    ]
                )
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful agent that can use SharePoint tools to assist users.\n            Use the available SharePoint tools to answer questions and perform tasks.",
                    tools=[sharepoint_tool],
                ),
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                stream_response = openai.responses.create(
                    stream=True,
                    tool_choice="required",
                    input="Please summarize the last meeting notes stored in SharePoint.",
                )
                for event in stream_response:
                    if event.type == "response.created":
                        print(
                            f"Follow-up response created with ID: {event.response.id}"
                        )
                    elif event.type == "response.output_text.delta":
                        print(f"Delta: {event.delta}")
                    elif event.type == "response.output_text.done":
                        print(f"\nFollow-up response done!")
                    elif event.type == "response.output_item.done":
                        if event.item.type == "message":
                            item = event.item
                            if item.content[-1].type == "output_text":
                                text_content = item.content[-1]
                                for annotation in text_content.annotations:
                                    if annotation.type == "url_citation":
                                        print(
                                            f"URL Citation: {annotation.url}, Start index: {annotation.start_index}, End index: {annotation.end_index}"
                                        )
                    elif event.type == "response.completed":
                        print(f"\nFollow-up completed!")
                        print(f"Full response: {event.response.output_text}")
    # </doc_sharepoint_prompt_agents>


def main():
    examples = {"aip-python-102": example_102}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-102")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
