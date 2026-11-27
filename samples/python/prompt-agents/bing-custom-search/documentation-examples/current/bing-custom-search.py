# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_076():
    # <doc_bing_tools_restrict_grounding_with_bing_custom_search_preview>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            BingCustomSearchPreviewTool,
            BingCustomSearchToolParameters,
            BingCustomSearchConfiguration,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        CUSTOM_SEARCH_CONNECTION_NAME = "my-custom-search-connection"
        CUSTOM_SEARCH_INSTANCE_NAME = "my-custom-search-instance"
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        bing_custom_connection = project.connections.get(CUSTOM_SEARCH_CONNECTION_NAME)
        bing_custom_search_tool = BingCustomSearchPreviewTool(
            bing_custom_search_preview=BingCustomSearchToolParameters(
                search_configurations=[
                    BingCustomSearchConfiguration(
                        project_connection_id=bing_custom_connection.id,
                        instance_name=CUSTOM_SEARCH_INSTANCE_NAME,
                    )
                ]
            )
        )
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model="gpt-4.1-mini",
                instructions="You are a helpful agent that can use Bing Custom Search tools to assist users. \n        Use the available Bing Custom Search tools to answer questions and perform tasks.",
                tools=[bing_custom_search_tool],
            ),
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        user_input = input(
            "Enter your question for the Bing Custom Search agent (e.g., 'Tell me more about foundry agent service'): \n"
        )
        stream_response = openai.responses.create(stream=True, input=user_input)
        for event in stream_response:
            if event.type == "response.created":
                print(f"Follow-up response created with ID: {event.response.id}")
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
    # </doc_bing_tools_restrict_grounding_with_bing_custom_search_preview>


def main():
    examples = {"aip-python-076": example_076}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-076")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
