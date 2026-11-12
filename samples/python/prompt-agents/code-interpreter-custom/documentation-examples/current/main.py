# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_085():
    # <doc_custom_code_interpreter_code_example>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MCPTool,
            MCPToolboxTool,
            PromptAgentDefinition,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "CustomCodeInterpreterAgent"
        MCP_SERVER_URL = os.environ["FOUNDRY_MCP_SERVER_URL"]
        MCP_CONNECTION_ID = os.environ["FOUNDRY_MCP_CONNECTION_ID"]
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            toolbox = project.toolboxes.create_version(
                name="custom-code-interpreter-toolbox",
                description="Toolbox with the custom code interpreter MCP server",
                tools=[
                    MCPToolboxTool(
                        server_label="custom-code-interpreter",
                        server_url=MCP_SERVER_URL,
                        project_connection_id=MCP_CONNECTION_ID,
                    )
                ],
            )
            TOOLBOX_MCP_URL = f"{PROJECT_ENDPOINT}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
            TOOLBOX_CONNECTION_NAME = "custom-code-interpreter-toolbox-conn"
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions="You are a helpful assistant that can run Python code to analyze data and solve problems.",
                    tools=[
                        MCPTool(
                            server_label="toolbox",
                            server_url=TOOLBOX_MCP_URL,
                            require_approval="never",
                            project_connection_id=TOOLBOX_CONNECTION_NAME,
                        )
                    ],
                ),
                description="Agent with custom code interpreter for data analysis.",
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                response = openai.responses.create(
                    input="Calculate the factorial of 10 using Python."
                )
                print(f"Response: {response.output_text}")
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            project.toolboxes.delete_version(name=toolbox.name, version=toolbox.version)
            print("Agent deleted")
    # </doc_custom_code_interpreter_code_example>


def main():
    examples = {"aip-python-085": example_085}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-085")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
