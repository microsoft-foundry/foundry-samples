# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_077():
    # <doc_browser_automation_prompt_agents>
    import os
    import json
    from util import create_version_with_endpoint
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        PromptAgentDefinition,
        BrowserAutomationTool,
        BrowserAutomationToolParameters,
        BrowserAutomationToolConnectionParameters,
    )

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ.get("FOUNDRY_AGENT_NAME") or "MyAgent"
    tool = BrowserAutomationTool(
        browser_automation=BrowserAutomationToolParameters(
            connection=BrowserAutomationToolConnectionParameters(
                project_connection_id=os.environ[
                    "FOUNDRY_BROWSER_AUTOMATION_PROJECT_CONNECTION_ID"
                ]
            )
        )
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        create_version_with_endpoint(
            project_client=project_client,
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                instructions="You are an Agent helping with browser automation tasks.\n        You can answer questions, provide information, and assist with various tasks\n        related to web browsing using the Browser Automation tool available to you.",
                tools=[tool],
            ),
        ),
        project_client.get_openai_client(agent_name=agent_name) as openai_client,
    ):
        stream_response = openai_client.responses.create(
            stream=True,
            input="\n        Use the Browser Automation tool to visit https://example.com.\n        Read the page and report its title and the visible description paragraph.\n        Base your answer on the browser results, not on prior knowledge.",
        )
        for event in stream_response:
            if event.type == "response.created":
                print(f"Response created with ID: {event.response.id}")
            elif event.type == "response.output_item.done":
                item = event.item
                if item.type == "remote_function_call":
                    arguments = json.loads(getattr(item, "arguments", None) or "{}")
                    arguments.pop("browserSessionId", None)
                    print(
                        f"Browser action: {item.name} (call ID: {item.call_id}), arguments: {arguments}"
                    )
            elif event.type == "response.output_text.done":
                print(f"\nAgent message: {event.text}")
            elif event.type == "response.completed":
                print("\nResponse completed!")
    # </doc_browser_automation_prompt_agents>


def main():
    examples = {"aip-python-077": example_077}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-077")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
