# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_083():
    # <doc_connectors_step_7_use_the_connection_from_your_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os

        CONNECTION_NAME = os.environ["FOUNDRY_CONNECTOR_CONNECTION_NAME"]
        SERVER_URL = os.environ["FOUNDRY_CONNECTOR_MCP_URL"]
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MCPTool,
            PromptAgentDefinition,
            MCPToolboxTool,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        TOOLBOX_CONNECTION_NAME = "connector-toolbox-conn"
        client = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        toolbox = client.toolboxes.create_version(
            name="connector-toolbox",
            description="Toolbox with the connector MCP server",
            tools=[
                MCPToolboxTool(
                    server_label=CONNECTION_NAME,
                    server_url=SERVER_URL,
                    project_connection_id=CONNECTION_NAME,
                    require_approval="never",
                )
            ],
        )
        TOOLBOX_MCP_URL = f"{PROJECT_ENDPOINT}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
        print(
            f"Configure the toolbox connection {TOOLBOX_CONNECTION_NAME!r} with endpoint: {TOOLBOX_MCP_URL}"
        )
        input(
            "Create or update that project connection using user Entra-token authentication, then press Enter to continue: "
        )
        toolbox_connection = client.connections.get(name=TOOLBOX_CONNECTION_NAME)
        if toolbox_connection.target != TOOLBOX_MCP_URL:
            raise ValueError(
                "The toolbox connection target does not match the created toolbox version. Update the connection before continuing."
            )
        toolbox_tool = MCPTool(
            server_label="toolbox",
            server_url=TOOLBOX_MCP_URL,
            project_connection_id=toolbox_connection.id,
            require_approval="never",
        )
        agent = client.agents.create_version(
            agent_name="my-connector-agent",
            definition=PromptAgentDefinition(
                model="gpt-4o",
                instructions="You are a helpful assistant.",
                tools=[toolbox_tool],
            ),
        )
        print(f"Created agent: {agent.name}, version: {agent.version}")
    # </doc_connectors_step_7_use_the_connection_from_your_agent>


def main():
    examples = {"aip-python-083": example_083}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-083")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
