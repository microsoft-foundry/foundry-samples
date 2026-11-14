"""Update session instructions, then request an out-of-band text response.

Set FOUNDRY_PROJECT_ENDPOINT; optionally set FOUNDRY_VOICE_AGENT_MODEL.
Run: python voice_agent_realtime_session.py
"""

import os
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeServerEventError,
    RealtimeServerEventResponseDone,
    RealtimeServerEventResponseTextDone,
    RealtimeServerEventSessionCreated,
    RealtimeServerEventSessionUpdated,
    VoiceAgentAudioConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentDefinition,
    VoiceAgentResponseCreateParams,
    VoiceAgentSessionUpdateConfig,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, safe_print, sample_agent_name


def run_session_overrides(connection: RealtimeConnection) -> None:
    deadline = time.monotonic() + 45
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The session did not start.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventSessionCreated):
            break
    connection.session.update(
        session=VoiceAgentSessionUpdateConfig(
            instructions="Keep replies brief.",
            audio=VoiceAgentAudioConfig(
                output=VoiceAgentAudioOutputConfig(
                    voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
                )
            ),
        )
    )
    deadline = time.monotonic() + 45
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The session update was not acknowledged.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if (
            isinstance(event, RealtimeServerEventSessionUpdated)
            and event.session.get("instructions") == "Keep replies brief."
        ):
            break

    # An empty input clears context for this response; "none" keeps it out of the conversation.
    connection.response.create(
        response=VoiceAgentResponseCreateParams(
            conversation="none",
            input=[],
            instructions="Say exactly: Hello from a temporary response.",
            output_modalities=[VoiceOutputModality.TEXT],
            max_output_tokens=64,
        )
    )
    deadline = time.monotonic() + 45
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The out-of-band response did not finish.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventResponseTextDone):
            safe_print(f"Agent: {event.text}")
        elif isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status != "completed":
                raise RuntimeError(
                    f"Voice response ended with status {event.response.status}."
                )
            return


def main() -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-session-overrides")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as client,
    ):
        require_new_agent(client, agent_name)
        created = client.agents.create_version(
            agent_name=agent_name,
            definition=VoiceAgentDefinition(
                model_type=VoiceModelType.MANAGED,
                model=model,
                instructions="You are a helpful voice assistant.",
                # A session cannot switch between native and Azure voice families.
                audio=VoiceAgentAudioConfig(
                    output=VoiceAgentAudioOutputConfig(
                        voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
                    )
                ),
            ),
        )
        try:
            with client.voice_agents.realtime.connect(
                agent_name=agent_name
            ) as connection:
                run_session_overrides(connection)
        finally:
            client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version
            )


if __name__ == "__main__":
    main()
