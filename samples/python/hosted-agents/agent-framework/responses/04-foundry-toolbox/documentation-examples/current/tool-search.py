# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_112():
    # <doc_tool_search_enable_tool_search>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import MCPToolboxTool, ToolSearchToolboxTool

        project = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        inner_mcp_tool = MCPToolboxTool(
            server_label="github",
            server_url="https://api.githubcopilot.com/mcp",
            require_approval="never",
            project_connection_id="github-mcp-conn",
        )
        toolbox_version = project.toolboxes.create_version(
            name="my-toolbox",
            description="Large toolbox with tool search enabled",
            tools=[inner_mcp_tool, ToolSearchToolboxTool()],
        )
        print(
            f"Created toolbox `{toolbox_version.name}` (version {toolbox_version.version})"
        )
    # </doc_tool_search_enable_tool_search>


def main():
    examples = {"aip-python-112": example_112}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-112")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
