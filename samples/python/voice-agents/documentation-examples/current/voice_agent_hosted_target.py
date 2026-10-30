# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_149():
    # <doc_voice_first_with_hosted_agent_create_the_voice_based_agent>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        RealtimeAudioFormatsAudioPcm,
        VoiceAgentAudioConfig,
        VoiceAgentAudioInputConfig,
        VoiceAgentAudioOutputConfig,
        VoiceAgentDefinition,
        VoiceAgentInputTranscription,
        VoiceAgentServerVadTurnDetection,
        VoiceAgentTemplateGreetingConfig,
        VoiceHostedAgentConversationEngine,
        VoiceOutputModality,
        VoiceType,
    )
    from azure.identity import DefaultAzureCredential

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    HOSTED_AGENT_NAME = os.environ["FOUNDRY_HOSTED_AGENT_NAME"]
    HOSTED_AGENT_VERSION = os.environ["FOUNDRY_HOSTED_AGENT_VERSION"]
    VOICE_AGENT_NAME = "hosted-conversation-voice-agent"
    conversation_engine = VoiceHostedAgentConversationEngine(name=HOSTED_AGENT_NAME)
    if HOSTED_AGENT_VERSION:
        conversation_engine.version = HOSTED_AGENT_VERSION
    voice_definition = VoiceAgentDefinition(
        conversation_engine=conversation_engine,
        greeting=VoiceAgentTemplateGreetingConfig(
            text="Hello! How can I help you today?"
        ),
        store=True,
        output_modalities=[VoiceOutputModality.AUDIO],
        audio=VoiceAgentAudioConfig(
            input=VoiceAgentAudioInputConfig(
                format=RealtimeAudioFormatsAudioPcm(rate=24000),
                turn_detection=VoiceAgentServerVadTurnDetection(
                    threshold=0.5, prefix_padding_ms=300, silence_duration_ms=1000
                ),
                transcription=VoiceAgentInputTranscription(model="azure-speech"),
            ),
            output=VoiceAgentAudioOutputConfig(
                format=RealtimeAudioFormatsAudioPcm(rate=24000),
                voice="en-US-JennyNeural",
                voice_type=VoiceType.AZURE_STANDARD,
            ),
        ),
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True
        ) as project_client,
    ):
        voice_agent = project_client.agents.create_version(
            agent_name=VOICE_AGENT_NAME,
            description="Voice agent that uses a hosted agent as its conversation engine",
            definition=voice_definition,
        )
        print(f"Voice agent created: {voice_agent.name}, version {voice_agent.version}")
    # </doc_voice_first_with_hosted_agent_create_the_voice_based_agent>


def main():
    examples = {"aip-python-149": example_149}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-149")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
