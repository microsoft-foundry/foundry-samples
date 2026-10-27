# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_096():
    # <doc_model_context_protocol_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import json
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, MCPTool
        from openai.types.responses.response_input_param import (
            McpApprovalResponse,
            ResponseInputParam,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        MCP_CONNECTION_NAME = "my-mcp-connection"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            tool = MCPTool(
                server_label="api-specs",
                server_url="https://api.githubcopilot.com/mcp",
                require_approval="always",
                project_connection_id=MCP_CONNECTION_NAME,
            )
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="Use MCP tools as needed",
                    tools=[tool],
                ),
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                print(f"Created conversation (id: {conversation.id})")
                response = openai.responses.create(
                    conversation=conversation.id,
                    input="What is my username in my GitHub profile?",
                )
                input_list: ResponseInputParam = []
                for item in response.output:
                    if item.type == "mcp_approval_request" and item.id:
                        print("MCP approval requested")
                        print(f"  Server: {item.server_label}")
                        print(f"  Tool: {getattr(item, 'name', '<unknown>')}")
                        print(
                            f"  Arguments: {json.dumps(getattr(item, 'arguments', None), indent=2, default=str)}"
                        )
                        should_approve = (
                            input("Approve this MCP tool call? (y/N): ").strip().lower()
                            == "y"
                        )
                        input_list.append(
                            McpApprovalResponse(
                                type="mcp_approval_response",
                                approve=should_approve,
                                approval_request_id=item.id,
                            )
                        )
                response = openai.responses.create(
                    input=input_list, previous_response_id=response.id
                )
                print(f"Response: {response.output_text}")
                openai.conversations.delete(conversation_id=conversation.id)
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            print("Agent deleted")
    # </doc_model_context_protocol_prompt_agents>


def main():
    examples = {"aip-python-096": example_096}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-096")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
