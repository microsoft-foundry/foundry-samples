"""Cancel a Realtime response and truncate unheard audio, without audio hardware.

Set FOUNDRY_PROJECT_ENDPOINT; optionally set FOUNDRY_VOICE_AGENT_MODEL.
Run: python voice_agent_realtime_interruption.py
"""

import os
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventConversationItemTruncated,
    RealtimeServerEventError,
    RealtimeServerEventResponseAudioDelta,
    RealtimeServerEventResponseDone,
    VoiceAgentDefinition,
    VoiceModelType,
    VoiceOutputModality,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, sample_agent_name


def interrupt_response(connection: RealtimeConnection) -> None:
    connection.conversation.item.create(
        item=RealtimeConversationItemMessageUser(
            type=RealtimeConversationItemType.MESSAGE,
            content=[
                RealtimeConversationItemMessageUserContent(
                    type="input_text", text="Count slowly from one to one hundred."
                )
            ],
        )
    )
    connection.response.create()
    interrupted = None
    cancelled = False
    truncated = False
    deadline = time.monotonic() + 45
    while not (cancelled and truncated):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "Cancellation and audio truncation were not both confirmed."
            )
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if (
            isinstance(event, RealtimeServerEventResponseAudioDelta)
            and interrupted is None
        ):
            interrupted = event
            connection.response.cancel(response_id=event.response_id)
            # Nothing is played here. A real player must use its actual heard duration.
            connection.conversation.item.truncate(
                item_id=event.item_id, content_index=event.content_index, audio_end_ms=0
            )
        elif isinstance(event, RealtimeServerEventResponseDone):
            if interrupted is None:
                raise RuntimeError(
                    "The response ended before any audio could be interrupted."
                )
            if event.response.id == interrupted.response_id:
                if event.response.status != "cancelled":
                    raise RuntimeError(
                        f"The interrupted response ended with status {event.response.status}."
                    )
                cancelled = True
        elif isinstance(event, RealtimeServerEventConversationItemTruncated):
            if (
                interrupted is not None
                and event.item_id == interrupted.item_id
                and event.content_index == interrupted.content_index
                and event.audio_end_ms == 0
            ):
                truncated = True
    print("Confirmed response cancellation and truncation of unheard audio.")


def main() -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-realtime-interruption")
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
                instructions="Speak slowly and follow the user's request.",
                output_modalities=[VoiceOutputModality.AUDIO],
            ),
        )
        try:
            with client.voice_agents.realtime.connect(
                agent_name=agent_name
            ) as connection:
                interrupt_response(connection)
        finally:
            client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version
            )


if __name__ == "__main__":
    main()
