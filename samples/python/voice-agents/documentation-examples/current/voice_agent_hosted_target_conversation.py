# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_150():
    # <doc_voice_first_with_hosted_agent_use_the_voice_based_agent>
    import os
    import asyncio
    import queue
    import threading
    import uuid
    import pyaudio
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.aio.operations import AsyncBetaRealtimeConnection
    from azure.ai.projects.models import (
        RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
        RealtimeServerEventError,
        RealtimeServerEventInputAudioBufferSpeechStarted,
        RealtimeServerEventResponseAudioDelta,
        RealtimeServerEventResponseAudioTranscriptDone,
        RealtimeServerEventResponseCreated,
        RealtimeServerEventSessionCreated,
        RealtimeServerEventSessionUpdated,
    )
    from azure.identity.aio import DefaultAzureCredential

    PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    VOICE_AGENT_NAME = "voice-live-bridge-basic-python-voice"
    SAMPLE_RATE = 24000
    CHANNELS = 1
    SAMPLE_WIDTH = 2
    CHUNK_FRAMES = 1200

    class AudioIO:
        def __init__(self, loop: asyncio.AbstractEventLoop):
            self.loop = loop
            self.audio = pyaudio.PyAudio()
            self.capture_queue: asyncio.Queue[bytes] = asyncio.Queue()
            self.playback_queue: queue.Queue[bytes] = queue.Queue()
            self.remaining_audio = b""
            self.playback_enabled = True
            self.playback_lock = threading.Lock()
            self.input_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_FRAMES,
                stream_callback=self._capture,
                start=False,
            )
            self.output_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True,
                frames_per_buffer=CHUNK_FRAMES,
                stream_callback=self._playback,
            )

        def _capture(self, audio, _frame_count, _time_info, _status):
            self.loop.call_soon_threadsafe(self.capture_queue.put_nowait, audio)
            return (None, pyaudio.paContinue)

        def _playback(self, _audio, frame_count, _time_info, _status):
            required_bytes = frame_count * SAMPLE_WIDTH
            with self.playback_lock:
                output = self.remaining_audio
                self.remaining_audio = b""
                while len(output) < required_bytes:
                    try:
                        output += self.playback_queue.get_nowait()
                    except queue.Empty:
                        output += bytes(required_bytes - len(output))
                self.remaining_audio = output[required_bytes:]
            return (output[:required_bytes], pyaudio.paContinue)

        def start_capture(self):
            self.input_stream.start_stream()

        def play(self, audio):
            with self.playback_lock:
                if self.playback_enabled:
                    self.playback_queue.put(audio)

        def start_response(self):
            with self.playback_lock:
                self.playback_enabled = True

        def stop_playback(self):
            with self.playback_lock:
                self.playback_enabled = False
                self.remaining_audio = b""
                while True:
                    try:
                        self.playback_queue.get_nowait()
                    except queue.Empty:
                        break

        def close(self):
            if self.input_stream.is_active():
                self.input_stream.stop_stream()
            self.input_stream.close()
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.audio.terminate()

    async def send_microphone_audio(
        connection: AsyncBetaRealtimeConnection, audio_io: AudioIO
    ):
        while True:
            audio = await audio_io.capture_queue.get()
            await connection.input_audio_buffer.append(audio=audio)

    async def receive_events(
        connection: AsyncBetaRealtimeConnection,
        audio_io: AudioIO,
        session_ready: asyncio.Event,
    ):
        async for event in connection:
            if isinstance(
                event,
                (RealtimeServerEventSessionCreated, RealtimeServerEventSessionUpdated),
            ):
                session_ready.set()
            elif isinstance(event, RealtimeServerEventInputAudioBufferSpeechStarted):
                audio_io.stop_playback()
            elif isinstance(event, RealtimeServerEventResponseCreated):
                audio_io.start_response()
            elif isinstance(
                event,
                RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
            ):
                print(f"You: {event.transcript}")
            elif isinstance(event, RealtimeServerEventResponseAudioDelta):
                audio_io.play(event.delta)
            elif isinstance(event, RealtimeServerEventResponseAudioTranscriptDone):
                print(f"Agent: {event.transcript}")
            elif isinstance(event, RealtimeServerEventError):
                raise RuntimeError(event.error.message)

    async def talk_to_agent():
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True
            ) as project_client,
            project_client.beta.voice_agents.realtime.connect(
                agent_name=VOICE_AGENT_NAME, agent_session_id=uuid.uuid4().hex
            ) as connection,
        ):
            session_ready = asyncio.Event()
            audio_io = AudioIO(asyncio.get_running_loop())
            receive_task = asyncio.create_task(
                receive_events(connection, audio_io, session_ready)
            )
            ready_task = asyncio.create_task(session_ready.wait())
            send_task = None
            try:
                done, _ = await asyncio.wait(
                    {ready_task, receive_task},
                    timeout=10,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in done:
                    receive_task.result()
                    raise ConnectionError(
                        "Connection closed before the session was ready."
                    )
                if ready_task not in done:
                    raise TimeoutError(
                        "The voice session wasn't ready within 10 seconds."
                    )
                print("Connected. Start speaking. Press Ctrl+C to stop.")
                audio_io.start_capture()
                send_task = asyncio.create_task(
                    send_microphone_audio(connection, audio_io)
                )
                done, _ = await asyncio.wait(
                    {send_task, receive_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    task.result()
            finally:
                tasks = [ready_task, receive_task]
                if send_task is not None:
                    tasks.append(send_task)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                audio_io.close()

    try:
        asyncio.run(talk_to_agent())
    except KeyboardInterrupt:
        print("Conversation ended.")
    # </doc_voice_first_with_hosted_agent_use_the_voice_based_agent>


def main():
    examples = {"aip-python-150": example_150}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-150")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
