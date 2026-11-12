# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_111():
    # <doc_tool_authentication_2_add_both_tools_to_a_toolbox>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import MCPToolboxTool, WorkIQPreviewToolboxTool

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        orders_connection = project.connections.get("orders-mcp")
        workiq_connection = project.connections.get("workiq-conn")
        toolbox_version = project.toolboxes.create_version(
            name="employee-toolbox",
            description="Private orders MCP + Work IQ, both via OAuth identity passthrough.",
            tools=[
                MCPToolboxTool(
                    server_label="orders",
                    server_url="https://orders-mcp.example.com/mcp",
                    require_approval="never",
                    project_connection_id=orders_connection.id,
                ),
                WorkIQPreviewToolboxTool(project_connection_id=workiq_connection.id),
            ],
        )
        print(
            f"Created toolbox: {toolbox_version.name}, version: {toolbox_version.version}"
        )
    # </doc_tool_authentication_2_add_both_tools_to_a_toolbox>


def main():
    examples = {"aip-python-111": example_111}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-111")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
