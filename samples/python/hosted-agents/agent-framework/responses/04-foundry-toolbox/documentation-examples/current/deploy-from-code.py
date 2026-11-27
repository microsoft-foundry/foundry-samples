# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_140():
    # <doc_quickstart_toolbox_agent_4_deploy_the_hosted_agent_with_python>
    from code_bundle import create_code_zip
    from azure.core.exceptions import ResourceNotFoundError
    import os
    import tempfile
    import time
    import zipfile
    from pathlib import Path
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        CodeConfiguration,
        CodeDependencyResolution,
        FixedRatioVersionSelectionRule,
        HostedAgentDefinition,
        ProtocolConfiguration,
        ProtocolVersionRecord,
        ResponsesProtocolConfiguration,
        VersionSelector,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model_name = os.environ["FOUNDRY_MODEL_NAME"]
    agent_name = os.environ.get("FOUNDRY_HOSTED_AGENT_NAME", "toolbox-agent")
    toolbox_name = os.environ["FOUNDRY_TOOLBOX_NAME"]
    sample_path = Path(os.environ["FOUNDRY_SAMPLE_PATH"]).resolve()

    def wait_for_active_version(project_client: AIProjectClient, version: str) -> None:
        for attempt in range(60):
            time.sleep(10)
            details = project_client.agents.get_version(
                agent_name=agent_name, agent_version=version
            )
            status = details["status"]
            print(f"Provisioning status: {status} (attempt {attempt + 1}/60)")
            if status == "active":
                return
            if status == "failed":
                raise RuntimeError(f"Hosted agent provisioning failed: {dict(details)}")
        raise RuntimeError(
            "Timed out waiting for the hosted agent version to become active."
        )

    code_zip_path = create_code_zip(sample_path)
    try:
        with (
            code_zip_path.open("rb") as code_stream,
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        ):
            try:
                previous_agent = project_client.agents.get(agent_name=agent_name)
            except ResourceNotFoundError:
                previous_agent = None
            original_agent_endpoint = (
                None if previous_agent is None else previous_agent.agent_endpoint
            )
            if previous_agent is not None and original_agent_endpoint is None:
                raise ValueError(
                    "Use a new agent name or an existing agent with a configured endpoint, so its original endpoint can be restored."
                )
            created = None
            try:
                created = project_client.agents.create_version_from_code(
                    agent_name=agent_name,
                    description="Hosted agent with Foundry Toolbox integration.",
                    definition=HostedAgentDefinition(
                        cpu="1",
                        memory="2Gi",
                        code_configuration=CodeConfiguration(
                            runtime="python_3_13",
                            entry_point=["python", "main.py"],
                            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
                        ),
                        environment_variables={
                            "FOUNDRY_PROJECT_ENDPOINT": endpoint,
                            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_name,
                            "TOOLBOX_NAME": toolbox_name,
                            "PYTHONNOUSERSITE": "1",
                        },
                        protocol_versions=[
                            ProtocolVersionRecord(protocol="responses", version="2.0.0")
                        ],
                    ),
                    code=code_stream,
                )
                print(f"Created hosted agent version {created.version}")
                wait_for_active_version(project_client, created.version)
                project_client.agents.update_details(
                    agent_name=agent_name,
                    agent_endpoint=AgentEndpointConfig(
                        version_selector=VersionSelector(
                            version_selection_rules=[
                                FixedRatioVersionSelectionRule(
                                    agent_version=created.version,
                                    traffic_percentage=100,
                                )
                            ]
                        ),
                        protocol_configuration=ProtocolConfiguration(
                            responses=ResponsesProtocolConfiguration()
                        ),
                    ),
                )
                with project_client.get_openai_client(
                    agent_name=agent_name
                ) as openai_client:
                    response = openai_client.responses.create(
                        input="How do I create a hosted agent in Microsoft Foundry? Use the Microsoft Learn documentation."
                    )
                    if response.status != "completed":
                        raise RuntimeError(f"Agent invocation failed: {response.error}")
                    print(response.output_text)
            finally:
                if original_agent_endpoint is not None:
                    project_client.agents.update_details(
                        agent_name=agent_name, agent_endpoint=original_agent_endpoint
                    )
                if created is not None:
                    if previous_agent is None:
                        project_client.agents.delete(agent_name=agent_name, force=True)
                    else:
                        project_client.agents.delete_version(
                            agent_name=agent_name,
                            agent_version=created.version,
                            force=True,
                        )
    finally:
        code_zip_path.unlink(missing_ok=True)
    # </doc_quickstart_toolbox_agent_4_deploy_the_hosted_agent_with_python>


def main():
    examples = {"aip-python-140": example_140}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-140")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
