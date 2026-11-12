# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_050():
    # <doc_enable_agent_to_agent_endpoint_enable_incoming_a2a>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            A2AProtocolConfiguration,
            AgentCard,
            AgentCardSkill,
            AgentEndpointConfig,
            ProtocolConfiguration,
            ResponsesProtocolConfiguration,
        )

        project = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        patched_agent = project.agents.update_details(
            agent_name=os.environ["FOUNDRY_AGENT_NAME"],
            agent_endpoint=AgentEndpointConfig(
                protocol_configuration=ProtocolConfiguration(
                    responses=ResponsesProtocolConfiguration(),
                    a2a=A2AProtocolConfiguration(),
                )
            ),
            agent_card=AgentCard(
                version="1.0",
                description="A helpful assistant that answers questions.",
                skills=[
                    AgentCardSkill(
                        id="general-qa",
                        name="General Q&A",
                        description="Answers general questions.",
                    )
                ],
            ),
        )
        print(f"Enabled incoming A2A for agent: {patched_agent.name}")
    # </doc_enable_agent_to_agent_endpoint_enable_incoming_a2a>


def main():
    examples = {"aip-python-050": example_050}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-050")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
