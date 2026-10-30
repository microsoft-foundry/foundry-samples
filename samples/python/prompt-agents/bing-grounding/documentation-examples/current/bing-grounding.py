# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_074():
    # <doc_bing_tools_ground_responses_with_bing_search>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            BingGroundingTool,
            BingGroundingSearchToolParameters,
            BingGroundingSearchConfiguration,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        BING_CONNECTION_NAME = "my-bing-connection"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            bing_connection = project.connections.get(BING_CONNECTION_NAME)
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful assistant.",
                    tools=[
                        BingGroundingTool(
                            bing_grounding=BingGroundingSearchToolParameters(
                                search_configurations=[
                                    BingGroundingSearchConfiguration(
                                        project_connection_id=bing_connection.id
                                    )
                                ]
                            )
                        )
                    ],
                ),
                description="You are a helpful agent.",
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                stream_response = openai.responses.create(
                    stream=True,
                    tool_choice="required",
                    input="What is today's date and weather in Seattle?",
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
                                        print(f"URL Citation: {annotation.url}")
                    elif event.type == "response.completed":
                        print(f"\nFollow-up completed!")
                        print(f"Full response: {event.response.output_text}")
    # </doc_bing_tools_ground_responses_with_bing_search>


def main():
    examples = {"aip-python-074": example_074}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-074")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
