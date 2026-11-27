# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_123():
    # <doc_use_subagent_voice_first_agent_create_a_subagent>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_SUBAGENT_MODEL"]
    definition = PromptAgentDefinition(
        model=model,
        instructions="You are a poetry-writing agent. Write an original poem that matches the user's requested topic, style, tone, and length. When the request doesn't specify these details, write a short poem in free verse. Return only the poem.",
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        poetry_agent = project_client.agents.create_version(
            agent_name="poetry-agent", definition=definition
        )
        print(f"Created subagent '{poetry_agent.name}', version {poetry_agent.version}")
    # </doc_use_subagent_voice_first_agent_create_a_subagent>


def example_124():
    # <doc_use_subagent_voice_first_agent_use_the_subagent_in_the_voice_based_agent>
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
        VoiceAgentSubagent,
        VoiceAgentSubagentConfig,
        VoiceAgentSubagentResponsePolicy,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_MODEL", "gpt-realtime")
    definition = VoiceAgentDefinition(
        model_type="managed",
        model=model,
        instructions="Answer ordinary questions yourself. When the user asks for a poem, always call forward_to_subagent for the configured poetry agent. After the poetry agent returns, read the poem exactly as written.",
        store=True,
        output_modalities=["audio"],
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
                voice_type="azure-standard",
            ),
        ),
        subagent_config=VoiceAgentSubagentConfig(
            subagents=[
                VoiceAgentSubagent(
                    agent_name="poetry-agent",
                    agent_capabilities="Writes original poems based on the requested topic, style, tone, and length.",
                    response_policy=VoiceAgentSubagentResponsePolicy(
                        immediate_ack=True
                    ),
                )
            ]
        ),
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        voice_agent = project_client.agents.create_version(
            agent_name="poetry-voice-agent",
            definition=definition,
            description="Voice agent that delegates poetry requests",
        )
        print(
            f"Created voice agent '{voice_agent.name}', version {voice_agent.version}"
        )
    # </doc_use_subagent_voice_first_agent_use_the_subagent_in_the_voice_based_agent>


def main():
    examples = {"aip-python-123": example_123, "aip-python-124": example_124}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-123")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
