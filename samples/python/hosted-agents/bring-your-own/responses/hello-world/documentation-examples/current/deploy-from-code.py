# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_048():
    # <doc_deploy_hosted_agent_code_create_the_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import hashlib
        from pathlib import Path
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            CodeConfiguration,
            HostedAgentDefinition,
            ProtocolVersionRecord,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "my-code-agent"
        ZIP_PATH = Path(os.environ["FOUNDRY_AGENT_CODE_ZIP_PATH"])
        code_zip_bytes = ZIP_PATH.read_bytes()
        code_zip_sha256 = hashlib.sha256(code_zip_bytes).hexdigest()
        credential = _resources.enter_context(DefaultAzureCredential())
        project = _resources.enter_context(
            AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
        )
        with ZIP_PATH.open("rb") as code_stream:
            created = project.agents.create_version_from_code(
                agent_name=AGENT_NAME,
                definition=HostedAgentDefinition(
                    cpu="1",
                    memory="2Gi",
                    code_configuration=CodeConfiguration(
                        runtime="python_3_13",
                        entry_point=["python", "main.py"],
                        dependency_resolution="remote_build",
                    ),
                    protocol_versions=[
                        ProtocolVersionRecord(protocol="responses", version="2.0.0")
                    ],
                    environment_variables={
                        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-5.4-mini"
                    },
                ),
                code=code_stream,
                code_zip_sha256=code_zip_sha256,
                description="Hello-world code agent",
            )
        print(f"Created version: {created.version}")
    # </doc_deploy_hosted_agent_code_create_the_agent>


def example_133():
    # <doc_quickstart_hosted_agent_step_4_deploy_the_hosted_agent_with_python>
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
    agent_name = os.environ.get("FOUNDRY_HOSTED_AGENT_NAME", "basic-agent")
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
                    description="Basic hosted agent deployed from local Python source.",
                    definition=HostedAgentDefinition(
                        cpu="0.5",
                        memory="1Gi",
                        code_configuration=CodeConfiguration(
                            runtime="python_3_14",
                            entry_point=["python", "main.py"],
                            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
                        ),
                        environment_variables={
                            "FOUNDRY_PROJECT_ENDPOINT": endpoint,
                            "FOUNDRY_MODEL_NAME": model_name,
                            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_name,
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
                print(f"Agent endpoint configured for version {created.version}")
                with project_client.get_openai_client(
                    agent_name=agent_name
                ) as openai_client:
                    response = openai_client.responses.create(
                        input="Write a haiku about deploying cloud applications."
                    )
                print(f"Agent response: {response.output_text}")
            finally:
                if original_agent_endpoint is not None:
                    project_client.agents.update_details(
                        agent_name=agent_name, agent_endpoint=original_agent_endpoint
                    )
                    print("Agent endpoint restored")
                if created is not None:
                    if previous_agent is None:
                        project_client.agents.delete(agent_name=agent_name, force=True)
                    else:
                        project_client.agents.delete_version(
                            agent_name=agent_name,
                            agent_version=created.version,
                            force=True,
                        )
                    print(f"Deleted hosted agent version {created.version}")
    finally:
        code_zip_path.unlink(missing_ok=True)
    # </doc_quickstart_hosted_agent_step_4_deploy_the_hosted_agent_with_python>


def main():
    examples = {"aip-python-048": example_048, "aip-python-133": example_133}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-048")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
