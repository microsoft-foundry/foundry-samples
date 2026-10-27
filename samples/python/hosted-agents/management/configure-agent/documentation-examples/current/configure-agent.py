# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_044():
    # <doc_configure_agent_select_the_active_agent_version>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AgentEndpointConfig,
            FixedRatioVersionSelectionRule,
            VersionSelector,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        agent_name = "name-of-your-existing-agent"
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        with project_client:
            endpoint_config = AgentEndpointConfig(
                version_selector=VersionSelector(
                    version_selection_rules=[
                        FixedRatioVersionSelectionRule(
                            agent_version="2", traffic_percentage=100
                        )
                    ]
                )
            )
            patched_agent = project_client.agents.update_details(
                agent_name=agent_name, agent_endpoint=endpoint_config
            )
            print(f"Agent endpoint configured for agent: {patched_agent.name}")
    # </doc_configure_agent_select_the_active_agent_version>


def example_045():
    # <doc_configure_agent_enable_protocols_and_authorization_schemes>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            A2AProtocolConfiguration,
            ActivityProtocolConfiguration,
            AgentEndpointConfig,
            BotServiceRbacAuthorizationScheme,
            EntraAuthorizationScheme,
            InvocationsProtocolConfiguration,
            ProtocolConfiguration,
            ResponsesProtocolConfiguration,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        agent_name = "name-of-your-existing-agent"
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        with project_client:
            endpoint_config = AgentEndpointConfig(
                protocol_configuration=ProtocolConfiguration(
                    responses=ResponsesProtocolConfiguration(),
                    activity=ActivityProtocolConfiguration(),
                    invocations=InvocationsProtocolConfiguration(),
                    a2a=A2AProtocolConfiguration(),
                ),
                authorization_schemes=[
                    EntraAuthorizationScheme(),
                    BotServiceRbacAuthorizationScheme(),
                ],
            )
            patched_agent = project_client.agents.update_details(
                agent_name=agent_name, agent_endpoint=endpoint_config
            )
            print(
                f"Protocols and authorization updated for agent: {patched_agent.name}"
            )
    # </doc_configure_agent_enable_protocols_and_authorization_schemes>


def example_046():
    # <doc_configure_agent_add_an_agent_card>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import AgentCard, AgentCardSkill
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "name-of-your-existing-agent"
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        patched_agent = project_client.agents.update_details(
            agent_name=AGENT_NAME,
            agent_card=AgentCard(
                version="1.0.0",
                description="A competitive intelligence analyst.",
                skills=[
                    AgentCardSkill(
                        id="competitor-analysis",
                        name="Competitor Analysis",
                        description="Analyzes competitor products and market positioning.",
                        tags=["research", "analysis", "market-intel"],
                        examples=["Compare our pricing with a competitor."],
                    )
                ],
            ),
        )
        print(f"Added an agent card to: {patched_agent.name}")
    # </doc_configure_agent_add_an_agent_card>


def main():
    examples = {
        "aip-python-044": example_044,
        "aip-python-045": example_045,
        "aip-python-046": example_046,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-044")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
