# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_065():
    # <doc_structured_inputs_use_structured_inputs_with_mcp_servers>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MCPTool,
            PromptAgentDefinition,
            StructuredInputDefinition,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "mcp-dynamic-agent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            tool = MCPTool(
                server_label="{{server_label}}",
                server_url="{{server_url}}",
                require_approval="never",
                headers={"X-Project-ID": "{{project_id}}"},
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="You are a helpful development assistant for {{project_name}}.",
                    tools=[tool],
                    structured_inputs={
                        "project_name": StructuredInputDefinition(
                            description="Project name",
                            required=True,
                            schema={"type": "string"},
                        ),
                        "server_label": StructuredInputDefinition(
                            description="MCP server label",
                            required=True,
                            schema={"type": "string"},
                        ),
                        "server_url": StructuredInputDefinition(
                            description="MCP server URL",
                            required=True,
                            schema={"type": "string"},
                        ),
                        "project_id": StructuredInputDefinition(
                            description="Project identifier",
                            required=True,
                            schema={"type": "string"},
                        ),
                    },
                ),
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                response = openai.responses.create(
                    conversation=conversation.id,
                    input="List recent commits",
                    extra_body={
                        "structured_inputs": {
                            "project_name": "CloudSync API",
                            "server_label": "cloudsync-repo",
                            "server_url": "https://gitmcp.io/myorg/cloudsync-api",
                            "project_id": "proj_12345",
                        }
                    },
                )
                print(response.output_text)
    # </doc_structured_inputs_use_structured_inputs_with_mcp_servers>


def main():
    examples = {"aip-python-065": example_065}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-065")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
