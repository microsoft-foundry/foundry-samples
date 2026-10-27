# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_057():
    # <doc_migrate_from_voice_live_check_the_connection_with_python>
    import os
    import time
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        RealtimeServerEventError,
        RealtimeServerEventSessionCreated,
        RealtimeServerEventSessionUpdated,
    )
    from azure.identity import DefaultAzureCredential

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        ) as project_client,
    ):
        with project_client.beta.voice_agents.realtime.connect(
            agent_name=os.environ["FOUNDRY_VOICE_AGENT_NAME"],
            api_version="v1",
            extra_query={
                "x-agent-version-override": os.environ["FOUNDRY_VOICE_AGENT_VERSION"]
            },
        ) as connection:
            deadline = time.monotonic() + 45
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Voice session didn't become ready.")
                event = connection.recv(timeout=remaining)
                if isinstance(event, RealtimeServerEventError):
                    raise RuntimeError(event.error.message)
                if isinstance(event, RealtimeServerEventSessionCreated):
                    if event.conversation_id:
                        print(f"Conversation ID: {event.conversation_id}")
                elif isinstance(event, RealtimeServerEventSessionUpdated):
                    print("Voice session ready.")
                    break
    # </doc_migrate_from_voice_live_check_the_connection_with_python>


def example_130():
    # <doc_prompt_voice_agent_talk_to_the_agent>
    import os
    import wave
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        RealtimeConversationItemMessageUser,
        RealtimeConversationItemMessageUserContent,
        RealtimeConversationItemType,
        RealtimeServerEventError,
        RealtimeServerEventResponseAudioDelta,
        RealtimeServerEventResponseAudioTranscriptDone,
        RealtimeServerEventResponseDone,
        RealtimeServerEventSessionCreated,
        VoiceAgentDefinition,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    conversation_id = None
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        agent = project_client.agents.get(agent_name=agent_name)
        latest = agent.versions.latest
        definition = latest.definition
        if not isinstance(definition, VoiceAgentDefinition):
            raise TypeError("The agent must have a voice definition.")
        with project_client.beta.voice_agents.realtime.connect(
            agent_name=agent_name
        ) as conn:

            def receive_response() -> tuple[str | None, list[bytes]]:
                session_conversation_id: str | None = None
                chunks: list[bytes] = []
                while True:
                    event = conn.recv(timeout=45)
                    if isinstance(event, RealtimeServerEventSessionCreated):
                        session_conversation_id = event.conversation_id
                    elif isinstance(event, RealtimeServerEventResponseAudioDelta):
                        chunks.append(event.delta)
                    elif isinstance(
                        event, RealtimeServerEventResponseAudioTranscriptDone
                    ):
                        print(f"Agent: {event.transcript}")
                    elif isinstance(event, RealtimeServerEventError):
                        raise RuntimeError(event.error.message)
                    elif isinstance(event, RealtimeServerEventResponseDone):
                        if event.response.status != "completed":
                            raise RuntimeError(
                                f"Response status: {event.response.status}"
                            )
                        return (session_conversation_id, chunks)

            if definition.greeting is not None:
                conversation_id, _ = receive_response()
            conn.conversation.item.create(
                item=RealtimeConversationItemMessageUser(
                    type=RealtimeConversationItemType.MESSAGE,
                    content=[
                        RealtimeConversationItemMessageUserContent(
                            type="input_text",
                            text="Hi. In one sentence, what can you help me with?",
                        )
                    ],
                )
            )
            conn.response.create()
            response_conversation_id, audio_chunks = receive_response()
            conversation_id = response_conversation_id or conversation_id
    if not conversation_id:
        raise RuntimeError("No persisted conversation ID was returned.")
    if not audio_chunks:
        raise RuntimeError("No audio was returned for the user turn.")
    with wave.open("reply.wav", "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"".join(audio_chunks))
    print(f"Saved reply.wav ({len(audio_chunks)} audio chunks)")
    print(f"Conversation id: {conversation_id}")
    # </doc_prompt_voice_agent_talk_to_the_agent>


def main():
    examples = {"aip-python-057": example_057, "aip-python-130": example_130}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-057")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
