# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_113():
    # <doc_toolbox_create_a_toolbox_version>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MCPToolboxTool,
            ToolSearchToolboxTool,
            WebSearchToolboxTool,
        )

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        toolbox_version = project.toolboxes.create_version(
            name="my-toolbox",
            description="Toolbox with web search and an MCP server",
            tools=[
                WebSearchToolboxTool(),
                MCPToolboxTool(
                    server_label="myserver",
                    server_url=os.environ["FOUNDRY_MCP_SERVER_URL"],
                    require_approval="never",
                    project_connection_id="my-key-auth-connection",
                ),
                ToolSearchToolboxTool(),
            ],
        )
        print(
            f"Created toolbox: {toolbox_version.name}, version: {toolbox_version.version}"
        )
    # </doc_toolbox_create_a_toolbox_version>


def example_114():
    # <doc_toolbox_configure_guardrails>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import WebSearchToolboxTool

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        toolbox_version = project.toolboxes.create_version(
            name="my-toolbox",
            description="Toolbox with guardrail",
            tools=[WebSearchToolboxTool()],
            policies={
                "rai_config": {"rai_policy_name": os.environ["FOUNDRY_RAI_POLICY_ID"]}
            },
        )
        print(f"Created version: {toolbox_version.version}")
    # </doc_toolbox_configure_guardrails>


def example_139():
    # <doc_quickstart_toolbox_agent_step_3_create_the_toolbox_with_python>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPToolboxTool, WebSearchToolboxTool
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    toolbox_name = os.environ["FOUNDRY_TOOLBOX_NAME"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        created = project_client.toolboxes.create_version(
            name=toolbox_name,
            description="Toolbox with web search and Microsoft Learn MCP.",
            tools=[
                WebSearchToolboxTool(name="web_search", search_context_size="medium"),
                MCPToolboxTool(
                    server_label="mslearn",
                    server_url="https://learn.microsoft.com/api/mcp",
                    require_approval="never",
                ),
            ],
        )
        print(f"Created toolbox version {created.version} for {created.name}")
        mcp_endpoint = f"{endpoint}/toolboxes/{created.name}/versions/{created.version}/mcp?api-version=v1"
        print(f"Toolbox version: {created.version}")
        print(f"Toolbox MCP endpoint: {mcp_endpoint}")
    # </doc_quickstart_toolbox_agent_step_3_create_the_toolbox_with_python>


def example_141():
    # <doc_quickstart_toolbox_agent_clean_up_resources>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project_client,
    ):
        project_client.toolboxes.delete(name=os.environ["FOUNDRY_TOOLBOX_NAME"])
    # </doc_quickstart_toolbox_agent_clean_up_resources>


def main():
    examples = {
        "aip-python-113": example_113,
        "aip-python-114": example_114,
        "aip-python-139": example_139,
        "aip-python-141": example_141,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-113")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
