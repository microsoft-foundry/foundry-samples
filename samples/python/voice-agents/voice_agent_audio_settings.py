"""Focused audio recipes with a real, supplied WAV turn (no microphone required).

Install requirements.txt (azure-ai-projects==2.11.0). Set
FOUNDRY_PROJECT_ENDPOINT; optionally FOUNDRY_VOICE_AGENT_MODEL (gpt-realtime)
and FOUNDRY_VOICE_TEXT_MODEL (gpt-4.1-mini, for cascaded/interim recipes).
FOUNDRY_VOICE_INTERIM_MODEL optionally selects a faster LLM for interim speech.
Run: python voice_agent_audio_settings.py --recipe semantic-vad --audio-file question.wav --output-audio reply.wav

Input must be PCM16 mono 24 kHz. Transcription recipes accept
FOUNDRY_VOICE_LANGUAGE (en-US) and comma-separated FOUNDRY_VOICE_PHRASES.
custom-speech additionally requires FOUNDRY_VOICE_CUSTOM_SPEECH_ENDPOINT_ID,
an existing authorized Custom Speech deployment; this sample provisions none.
Noise/echo config demonstrates server-reference cancellation with mono input.
Client-reference cancellation instead requires real interleaved reference audio.
Interim speech is conditional on latency, not guaranteed for every quick reply.
For an observable LLM interim on short questions, select a slower existing main
model (for example FOUNDRY_VOICE_TEXT_MODEL=gpt-5) and a faster interim model
(FOUNDRY_VOICE_INTERIM_MODEL=gpt-4.1-nano). This sample deploys neither model.
Managed Azure Speech requires Azure semantic VAD; cascaded recipes use this
pair. OpenAI semantic VAD uses gpt-4o-transcribe instead.
"""

import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    RealtimeAudioFormatsAudioPcm,
    VoiceAgentAudioConfig,
    VoiceAgentAudioInputConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentAzureSemanticVadEnTurnDetection,
    VoiceAgentAzureSemanticVadMultilingualTurnDetection,
    VoiceAgentAzureSemanticVadTurnDetection,
    VoiceAgentDefinition,
    VoiceAgentEchoCancellation,
    VoiceAgentInputTranscription,
    VoiceAgentInterimResponseTrigger,
    VoiceAgentLlmInterimResponseConfig,
    VoiceAgentNoiseReduction,
    VoiceAgentNoiseReductionType,
    VoiceAgentSemanticVadTurnDetection,
    VoiceAgentStaticInterimResponseConfig,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_realtime_audio_conversation_async import (
    read_pcm_wav,
    run_file_conversation,
)
from voice_agent_util import require_new_agent_async, sample_agent_name

VAD_RECIPES = (
    "semantic-vad",
    "azure-semantic-vad",
    "azure-semantic-vad-en",
    "azure-semantic-vad-multilingual",
)
RECIPES = VAD_RECIPES + (
    "noise-echo",
    "transcription",
    "transcription-hints",
    "custom-speech",
    "streaming-transcription",
    "interim-static",
    "interim-llm",
)
INTERIM_TEXT = "One moment while I check that."


def build_definition(recipe: str) -> VoiceAgentDefinition:
    """Use public 2.11.0 models, with provider-specific transcription settings."""
    if recipe not in RECIPES:
        raise ValueError(f"Unknown audio recipe: {recipe}")
    language = os.environ.get("FOUNDRY_VOICE_LANGUAGE") or "en-US"
    phrases = [
        text.strip()
        for text in os.environ.get("FOUNDRY_VOICE_PHRASES", "Foundry,Contoso").split(
            ","
        )
        if text.strip()
    ]
    audio_input = VoiceAgentAudioInputConfig(
        format=RealtimeAudioFormatsAudioPcm(rate=24000),
        turn_detection=None,
        transcription=VoiceAgentInputTranscription(
            model="gpt-4o-transcribe", language="en"
        ),
    )
    # Constructor None omits a field; an explicit JSON null disables default VAD.
    audio_input["turn_detection"] = None
    cascaded = recipe in (
        "streaming-transcription",
        "interim-static",
        "interim-llm",
    )
    definition = VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model=(
            os.environ.get("FOUNDRY_VOICE_TEXT_MODEL") or "gpt-4.1-mini"
            if cascaded
            else os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
        ),
        instructions="Answer the user's question briefly, in one friendly sentence.",
        store=False,
        audio=VoiceAgentAudioConfig(
            input=audio_input,
            output=VoiceAgentAudioOutputConfig(
                voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
            ),
        ),
        output_modalities=[VoiceOutputModality.AUDIO],
    )
    if recipe == "semantic-vad":
        audio_input.turn_detection = VoiceAgentSemanticVadTurnDetection(
            eagerness="medium", create_response=True, interrupt_response=True
        )
    elif recipe == "azure-semantic-vad":
        audio_input.turn_detection = VoiceAgentAzureSemanticVadTurnDetection(
            languages=["en-US"], create_response=True, interrupt_response=True
        )
    elif recipe == "azure-semantic-vad-en":
        audio_input.turn_detection = VoiceAgentAzureSemanticVadEnTurnDetection(
            create_response=True, interrupt_response=True
        )
    elif recipe == "azure-semantic-vad-multilingual":
        audio_input.turn_detection = (
            VoiceAgentAzureSemanticVadMultilingualTurnDetection(
                languages=["en-US", "es-ES"],
                create_response=True,
                interrupt_response=True,
            )
        )
    elif recipe == "noise-echo":
        mode = VoiceAgentNoiseReductionType(
            os.environ.get("FOUNDRY_VOICE_NOISE_REDUCTION")
            or "azure_deep_noise_suppression"
        )
        audio_input.noise_reduction = VoiceAgentNoiseReduction(type=mode)
        audio_input.echo_cancellation = VoiceAgentEchoCancellation(
            reference_source="server", channels=1
        )
    elif recipe in ("transcription", "custom-speech", "streaming-transcription"):
        transcription = VoiceAgentInputTranscription(
            model=(
                "azure-speech-streaming"
                if recipe == "streaming-transcription"
                else "azure-speech"
            ),
            language=language,
            phrase_list=phrases,
            profanity_filter="masked",
        )
        if recipe == "custom-speech":
            transcription.custom_speech = {
                language: os.environ["FOUNDRY_VOICE_CUSTOM_SPEECH_ENDPOINT_ID"]
            }
        audio_input.transcription = transcription
    elif recipe == "transcription-hints":
        audio_input.transcription = VoiceAgentInputTranscription(
            model="gpt-transcribe", languages=["en", "es"], keywords=phrases
        )
    elif recipe == "interim-static":
        definition.interim_response = VoiceAgentStaticInterimResponseConfig(
            triggers=[VoiceAgentInterimResponseTrigger.LATENCY],
            latency_threshold_ms=timedelta(milliseconds=1),
            texts=[INTERIM_TEXT],
        )
    elif recipe == "interim-llm":
        definition.interim_response = VoiceAgentLlmInterimResponseConfig(
            triggers=[VoiceAgentInterimResponseTrigger.LATENCY],
            latency_threshold_ms=timedelta(milliseconds=1),
            model=os.environ.get("FOUNDRY_VOICE_INTERIM_MODEL") or "gpt-4.1-mini",
            instructions="Briefly acknowledge that you are checking the answer.",
            max_completion_tokens=32,
        )
    if recipe in (
        "azure-semantic-vad",
        "azure-semantic-vad-en",
        "azure-semantic-vad-multilingual",
        "noise-echo",
        "transcription",
        "custom-speech",
        "streaming-transcription",
        "interim-static",
        "interim-llm",
    ):
        if audio_input.turn_detection is None:
            audio_input.turn_detection = VoiceAgentAzureSemanticVadTurnDetection(
                create_response=True, interrupt_response=True
            )
        if recipe in VAD_RECIPES or recipe in (
            "noise-echo",
            "interim-static",
            "interim-llm",
        ):
            audio_input.transcription = VoiceAgentInputTranscription(
                model="azure-speech", language=language
            )
    return definition


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", choices=RECIPES, required=True)
    parser.add_argument("--audio-file", type=Path, required=True)
    parser.add_argument("--output-audio", type=Path, required=True)
    args = parser.parse_args()
    read_pcm_wav(args.audio_file)
    if args.output_audio.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output_audio}.")
    definition = build_definition(args.recipe)
    agent_name = sample_agent_name(f"sample-audio-{args.recipe}")
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
        ) as client,
    ):
        await require_new_agent_async(client, agent_name)
        created = None
        try:
            created = await client.agents.create_version(
                agent_name=agent_name, definition=definition
            )
            result = await run_file_conversation(
                client,
                agent_name,
                args.audio_file,
                args.output_audio,
                use_vad=(
                    definition.audio is not None
                    and definition.audio.input is not None
                    and definition.audio.input.turn_detection is not None
                ),
            )
            print(
                json.dumps(
                    {
                        "recipe": args.recipe,
                        **{
                            key: value
                            for key, value in result.items()
                            if key != "response_transcripts"
                        },
                    }
                )
            )
        finally:
            if created is not None:
                await client.agents.delete_version(
                    agent_name=agent_name, agent_version=created.version
                )


if __name__ == "__main__":
    asyncio.run(main())
