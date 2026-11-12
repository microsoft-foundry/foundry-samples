# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_069():
    # <doc_agent_to_agent_hosted_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import asyncio
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient, FoundryToolbox
        from azure.identity import AzureCliCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import A2AProtocolVersion, A2AToolboxTool

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        A2A_CONNECTION_NAME = "my-a2a-connection"
        credential = _resources.enter_context(AzureCliCredential())
        project = _resources.enter_context(
            AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
        )
        a2a_connection = project.connections.get(A2A_CONNECTION_NAME)
        toolbox = project.toolboxes.create_version(
            name="a2a-toolbox",
            description="Toolbox with the A2A tool",
            tools=[
                A2AToolboxTool(
                    a2a_version=A2AProtocolVersion.V1_0,
                    project_connection_id=a2a_connection.id,
                )
            ],
        )
    # </doc_agent_to_agent_hosted_agents>


def main():
    examples = {"aip-python-069": example_069}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-069")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
