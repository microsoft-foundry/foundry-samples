# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_064():
    # <doc_structured_inputs_use_structured_inputs_with_azure_ai_search>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AISearchIndexResource,
            AzureAISearchQueryType,
            AzureAISearchTool,
            AzureAISearchToolResource,
            PromptAgentDefinition,
            StructuredInputDefinition,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "aisearch-agent-structured-input"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            tool = AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=os.environ[
                                "FOUNDRY_AI_SEARCH_PROJECT_CONNECTION_ID"
                            ],
                            index_name=os.environ["FOUNDRY_AI_SEARCH_INDEX_NAME"],
                            query_type=AzureAISearchQueryType.SIMPLE,
                            filter="search.ismatchscoring('{{userFilter}}')",
                        )
                    ]
                )
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="You are a helpful assistant. You must always provide citations for answers using the tool and render them as: `【message_idx:search_idx†source】`.",
                    tools=[tool],
                    structured_inputs={
                        "userFilter": StructuredInputDefinition(
                            description="The user's search filter",
                            required=True,
                            schema={"type": "string"},
                        )
                    },
                ),
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                stream_response = openai.responses.create(
                    stream=True,
                    tool_choice="required",
                    input="What outdoor gear do you have?",
                    extra_body={"structured_inputs": {"userFilter": "boots"}},
                )
                for event in stream_response:
                    if event.type == "response.completed":
                        print(f"Agent response: {event.response.output_text}")
    # </doc_structured_inputs_use_structured_inputs_with_azure_ai_search>


def main():
    examples = {"aip-python-064": example_064}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-064")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
