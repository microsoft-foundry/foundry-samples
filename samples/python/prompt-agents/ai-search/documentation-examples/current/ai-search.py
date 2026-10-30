# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_070():
    # <doc_ai_search_add_azure_ai_search_to_a_toolbox>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AzureAISearchTool,
            PromptAgentDefinition,
            AzureAISearchToolResource,
            AISearchIndexResource,
            AzureAISearchQueryType,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        SEARCH_CONNECTION_NAME = "my-search-connection"
        SEARCH_INDEX_NAME = "my-search-index"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            azs_connection = project.connections.get(SEARCH_CONNECTION_NAME)
            connection_id = azs_connection.id
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful assistant. You must always provide citations for\n            answers using the tool and render them as: `[message_idx:search_idx†source]`.",
                    tools=[
                        AzureAISearchTool(
                            azure_ai_search=AzureAISearchToolResource(
                                indexes=[
                                    AISearchIndexResource(
                                        project_connection_id=connection_id,
                                        index_name=SEARCH_INDEX_NAME,
                                        query_type=AzureAISearchQueryType.SIMPLE,
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
                user_input = input(
                    "Enter your question for the AI Search agent available in the index\n            (e.g., 'Tell me about the mental health services available from Premera'): \n"
                )
                stream_response = openai.responses.create(
                    stream=True, tool_choice="required", input=user_input
                )
                for event in stream_response:
                    if event.type == "response.output_text.delta":
                        print(event.delta, end="")
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
                        print(f"\nFull response: {event.response.output_text}")
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            print("Agent deleted")
    # </doc_ai_search_add_azure_ai_search_to_a_toolbox>


def example_072():
    # <doc_ai_search_confirm_the_connection_id>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        SEARCH_CONNECTION_NAME = "my-search-connection"
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        connection = project.connections.get(SEARCH_CONNECTION_NAME)
        print(connection.id)
    # </doc_ai_search_confirm_the_connection_id>


def main():
    examples = {"aip-python-070": example_070, "aip-python-072": example_072}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-070")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
