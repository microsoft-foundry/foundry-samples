# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_117():
    # <doc_web_search_create_the_toolbox_and_domain_restricted_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            WebSearchToolboxTool,
            WebSearchConfiguration,
            MCPTool,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        BING_CUSTOM_SEARCH_CONNECTION_ID = os.environ[
            "FOUNDRY_BING_CUSTOM_SEARCH_CONNECTION_ID"
        ]
        BING_CUSTOM_SEARCH_INSTANCE_NAME = os.environ[
            "FOUNDRY_BING_CUSTOM_SEARCH_INSTANCE_NAME"
        ]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        toolbox = project.toolboxes.create_version(
            name="web-search-toolbox",
            description="Toolbox with the web search tool",
            tools=[
                WebSearchToolboxTool(
                    custom_search_configuration=WebSearchConfiguration(
                        project_connection_id=BING_CUSTOM_SEARCH_CONNECTION_ID,
                        instance_name=BING_CUSTOM_SEARCH_INSTANCE_NAME,
                    )
                )
            ],
        )
        TOOLBOX_MCP_URL = f"{PROJECT_ENDPOINT}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
        TOOLBOX_CONNECTION_NAME = "web-search-toolbox-conn"
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful assistant that can search the web",
                tools=[
                    MCPTool(
                        server_label="toolbox",
                        server_url=TOOLBOX_MCP_URL,
                        require_approval="never",
                        project_connection_id=TOOLBOX_CONNECTION_NAME,
                    )
                ],
            ),
            description="Agent for domain-restricted web search.",
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        stream_response = openai.responses.create(
            stream=True,
            tool_choice="required",
            input="What are the latest updates from Microsoft Learn?",
        )
        for event in stream_response:
            if event.type == "response.created":
                print(f"Response created with ID: {event.response.id}")
            elif event.type == "response.output_text.delta":
                print(f"Delta: {event.delta}")
            elif event.type == "response.output_text.done":
                print(f"\nResponse done!")
            elif event.type == "response.output_item.done":
                if event.item.type == "message":
                    item = event.item
                    if item.content[-1].type == "output_text":
                        text_content = item.content[-1]
                        for annotation in text_content.annotations:
                            if annotation.type == "url_citation":
                                print(f"URL Citation: {annotation.url}")
            elif event.type == "response.completed":
                print(f"\nResponse completed!")
                print(f"Full response: {event.response.output_text}")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        print("Agent deleted")
    # </doc_web_search_create_the_toolbox_and_domain_restricted_agent>


def main():
    examples = {"aip-python-117": example_117}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-117")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
