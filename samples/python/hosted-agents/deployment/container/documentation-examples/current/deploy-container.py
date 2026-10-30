# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_049():
    # <doc_deploy_hosted_agent_create_a_hosted_agent_version>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AgentEndpointProtocol,
            ContainerConfiguration,
            HostedAgentDefinition,
            ProtocolVersionRecord,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        credential = _resources.enter_context(DefaultAzureCredential())
        project = _resources.enter_context(
            AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
        )
        agent = project.agents.create_version(
            agent_name="my-agent",
            definition=HostedAgentDefinition(
                protocol_versions=[
                    ProtocolVersionRecord(
                        protocol=AgentEndpointProtocol.RESPONSES, version="2.0.0"
                    )
                ],
                cpu="1",
                memory="2Gi",
                container_configuration=ContainerConfiguration(
                    image=os.environ["FOUNDRY_CONTAINER_IMAGE"]
                ),
                environment_variables={"MODEL_DEPLOYMENT_NAME": "gpt-5-mini"},
            ),
        )
        print(f"Agent created: {agent.name}, version: {agent.version}")
    # </doc_deploy_hosted_agent_create_a_hosted_agent_version>


def main():
    examples = {"aip-python-049": example_049}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-049")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
