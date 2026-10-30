# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_118():
    # <doc_web_search_create_the_deep_research_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, WebSearchPreviewTool

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyDeepResearchAgent"
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=AGENT_NAME)
        )
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model="o3-deep-research",
                instructions="You are a helpful assistant that can search the web",
                tools=[WebSearchPreviewTool()],
            ),
            description="Agent for deep research with web search.",
        )
        print(
            f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
        )
        conversation = openai.conversations.create()
        print(f"Created conversation (id: {conversation.id})")
        stream_response = openai.responses.create(
            stream=True,
            conversation=conversation.id,
            input="What are the latest advancements in quantum computing?",
        )
        for event in stream_response:
            if event.type == "response.created":
                print(f"Response created with ID: {event.response.id}")
            elif event.type == "response.output_text.delta":
                print(f"Delta: {event.delta}")
            elif event.type == "response.output_text.done":
                print(f"\nResponse done!")
            elif event.type == "response.completed":
                print(f"\nResponse completed!")
                print(f"Full response: {event.response.output_text}")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        print("Agent deleted")
    # </doc_web_search_create_the_deep_research_agent>


def main():
    examples = {"aip-python-118": example_118}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-118")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
