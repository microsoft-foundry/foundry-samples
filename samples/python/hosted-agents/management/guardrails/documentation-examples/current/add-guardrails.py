# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_041():
    # <doc_add_hosted_agent_guardrails_add_a_guardrail>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AgentEndpointProtocol,
            ContainerConfiguration,
            HostedAgentDefinition,
            ProtocolVersionRecord,
            RaiConfig,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        RAI_POLICY_ID = os.environ["FOUNDRY_RAI_POLICY_ID"]
        credential = _resources.enter_context(DefaultAzureCredential())
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True
            )
        )
        agent = project.agents.create_version(
            agent_name="my-agent",
            definition=HostedAgentDefinition(
                cpu="1",
                memory="2Gi",
                container_configuration=ContainerConfiguration(
                    image=os.environ["FOUNDRY_CONTAINER_IMAGE"]
                ),
                protocol_versions=[
                    ProtocolVersionRecord(
                        protocol=AgentEndpointProtocol.RESPONSES, version="2.0.0"
                    )
                ],
                rai_config=RaiConfig(rai_policy_name=RAI_POLICY_ID),
            ),
        )
        print(f"Agent created: {agent.name}, version: {agent.version}")
    # </doc_add_hosted_agent_guardrails_add_a_guardrail>


def main():
    examples = {"aip-python-041": example_041}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-041")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
