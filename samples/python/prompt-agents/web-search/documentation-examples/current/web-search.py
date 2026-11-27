# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_032():
    # <doc_runtime_components_create_an_agent_with_tools>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, WebSearchTool

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = project.agents.create_version(
            agent_name="my-tool-agent",
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful assistant that can search the web.",
                tools=[WebSearchTool()],
            ),
        )
        print(f"Agent: {agent.name}, Version: {agent.version}")
    # </doc_runtime_components_create_an_agent_with_tools>


def example_115():
    # <doc_web_search_create_the_agent_and_run_a_search>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            WebSearchTool,
            WebSearchApproximateLocation,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="You are a helpful assistant that can search the web",
                    tools=[
                        WebSearchTool(
                            user_location=WebSearchApproximateLocation(
                                country="GB", city="London", region="London"
                            )
                        )
                    ],
                ),
                description="Agent for web search.",
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
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            print("Agent deleted")
    # </doc_web_search_create_the_agent_and_run_a_search>


def main():
    examples = {"aip-python-032": example_032, "aip-python-115": example_115}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-032")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
