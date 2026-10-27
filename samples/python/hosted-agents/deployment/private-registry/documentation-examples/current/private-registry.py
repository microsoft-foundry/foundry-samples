# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_059():
    # <doc_private_registry_connections_create_and_deploy_the_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            ContainerConfiguration,
            HostedAgentDefinition,
            ProtocolVersionRecord,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = project.agents.create_version(
            agent_name="private-registry-agent",
            definition=HostedAgentDefinition(
                cpu="0.5",
                memory="1Gi",
                container_configuration=ContainerConfiguration(
                    image=os.environ["FOUNDRY_CONTAINER_IMAGE"],
                    registry_connection_id="private-registry",
                ),
                protocol_versions=[
                    ProtocolVersionRecord(protocol="responses", version="2.0.0")
                ],
                environment_variables={
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": os.environ["FOUNDRY_MODEL_NAME"]
                },
            ),
        )
        print(f"Created {agent.name}, version {agent.version}")
    # </doc_private_registry_connections_create_and_deploy_the_agent>


def main():
    examples = {"aip-python-059": example_059}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-059")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
