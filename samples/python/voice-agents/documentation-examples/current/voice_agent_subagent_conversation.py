# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_125():
    # <doc_use_subagent_voice_first_agent_talk_to_the_voice_agent>
    import asyncio
    import os
    import pyaudio
    from azure.ai.projects import models
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.aio.operations import AsyncBetaRealtimeConnection
    from azure.identity.aio import DefaultAzureCredential

    RATE = 24000
    CHUNK = 2400

    async def wait_until_ready(connection: AsyncBetaRealtimeConnection) -> None:
        while True:
            event = await connection.recv()
            if isinstance(event, models.RealtimeServerEventSessionCreated):
                return
            if isinstance(event, models.RealtimeServerEventError):
                raise RuntimeError(event.error.message)

    async def send_microphone(
        connection: AsyncBetaRealtimeConnection, stream: pyaudio.Stream
    ) -> None:
        while True:
            audio = await asyncio.to_thread(
                stream.read, CHUNK, exception_on_overflow=False
            )
            await connection.input_audio_buffer.append(audio=audio)

    async def receive_audio(
        connection: AsyncBetaRealtimeConnection, stream: pyaudio.Stream
    ) -> None:
        async for event in connection:
            if isinstance(event, models.RealtimeServerEventResponseAudioDelta):
                await asyncio.to_thread(stream.write, event.delta)
            elif isinstance(
                event, models.RealtimeServerEventResponseAudioTranscriptDone
            ):
                print(f"Agent: {event.transcript}")
            elif isinstance(event, models.RealtimeServerEventError):
                raise RuntimeError(event.error.message)

    async def talk() -> None:
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        audio = pyaudio.PyAudio()
        microphone = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        speaker = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        try:
            async with (
                DefaultAzureCredential() as credential,
                AIProjectClient(
                    endpoint=endpoint, credential=credential, allow_preview=True
                ) as project_client,
                project_client.beta.voice_agents.realtime.connect(
                    agent_name="poetry-voice-agent"
                ) as connection,
            ):
                await asyncio.wait_for(wait_until_ready(connection), timeout=30)
                print("Connected. Ask the agent to write a poem.")
                await asyncio.gather(
                    send_microphone(connection, microphone),
                    receive_audio(connection, speaker),
                )
        finally:
            microphone.close()
            speaker.close()
            audio.terminate()

    asyncio.run(talk())
    # </doc_use_subagent_voice_first_agent_talk_to_the_voice_agent>


def main():
    examples = {"aip-python-125": example_125}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-125")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
