# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_047():
    # <doc_configure_voice_agent_save_and_test_the_agent>
    definition = VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model="gpt-realtime-2.1",
        instructions="You are a friendly voice assistant. Keep replies short and natural.",
    )
    from azure.ai.projects.models import VoiceAgentDefinition, VoiceModelType
    from azure.ai.projects.models import VoiceAgentDefinition, VoiceModelType
    import os
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        created = project_client.agents.create_version(
            agent_name=agent_name, definition=definition
        )
        print(f"Created voice agent '{agent_name}', version {created.version}")
    # </doc_configure_voice_agent_save_and_test_the_agent>


def example_128():
    # <doc_prompt_voice_agent_create_from_an_explicit_definition>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        VoiceAgentAudioConfig,
        VoiceAgentAudioOutputConfig,
        VoiceAgentDefinition,
        VoiceModelType,
        VoiceOutputModality,
        VoiceType,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL", "gpt-realtime")
    definition = VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model=model,
        instructions="You are a friendly voice assistant. Keep replies to one or two sentences.",
        audio=VoiceAgentAudioConfig(
            output=VoiceAgentAudioOutputConfig(
                voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
            )
        ),
        output_modalities=[VoiceOutputModality.AUDIO],
        store=True,
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        created = project_client.agents.create_version(
            agent_name=agent_name, definition=definition
        )
        print(f"Created voice agent '{agent_name}', version {created.version}")
    # </doc_prompt_voice_agent_create_from_an_explicit_definition>


def example_129():
    # <doc_prompt_voice_agent_create_with_a_self_deployed_model>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        VoiceAgentAudioConfig,
        VoiceAgentAudioOutputConfig,
        VoiceAgentDefinition,
        VoiceModelType,
        VoiceOutputModality,
        VoiceType,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    deployment_name = os.environ["FOUNDRY_VOICE_AGENT_MODEL"]
    definition = VoiceAgentDefinition(
        model_type=VoiceModelType.SELF_DEPLOYED,
        model=deployment_name,
        instructions="You are a helpful voice assistant. Keep replies short.",
        audio=VoiceAgentAudioConfig(
            output=VoiceAgentAudioOutputConfig(
                voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
            )
        ),
        output_modalities=[VoiceOutputModality.AUDIO],
        store=True,
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        created = project_client.agents.create_version(
            agent_name=agent_name, definition=definition
        )
        print(f"Created voice agent '{agent_name}', version {created.version}")
    # </doc_prompt_voice_agent_create_with_a_self_deployed_model>


def main():
    examples = {
        "aip-python-047": example_047,
        "aip-python-128": example_128,
        "aip-python-129": example_129,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-047")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
