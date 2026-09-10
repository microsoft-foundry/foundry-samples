#!/usr/bin/env python
# Copyright (c) Microsoft Corporation. All rights reserved.

"""Headless Voice Live smoke test for hosted-agent E2E validation.

This script is intended for CI. It connects to Azure Voice Live with an
AgentSessionConfig, streams a deterministic PCM16 WAV file as microphone input,
and waits for a non-empty agent response transcript.

Unlike the sample client under samples/python/hosted-agents, this script does
not use PyAudio and does not require microphone or speaker devices.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import os
import sys
import wave
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger("voicelive-e2e")
DEFAULT_AUDIO_FILE = Path(__file__).parent / "fixtures" / "voice-live-ci.wav"
SAMPLE_RATE = 24000
CHUNK_MS = 50
TAIL_SILENCE_MS = 1000
TIMEOUT_SECONDS = 90
VOICE_NAME = "en-US-Ava:DragonHDLatestNeural"
VAD_THRESHOLD = 0.5
VAD_PREFIX_PADDING_MS = 300
VAD_SILENCE_DURATION_MS = 500
INTERIM_LATENCY_MS = 500
EXPECTED_USER_TRANSCRIPT_CONTAINS = "voice live continuous integration"


def _read_pcm16_wav(path: Path) -> tuple[int, bytes]:
    """Read a mono PCM16 WAV file and return (sample_rate, pcm_bytes)."""
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        compression = wav_file.getcomptype()
        frames = wav_file.readframes(wav_file.getnframes())

    if compression != "NONE":
        raise ValueError(f"Unsupported WAV compression {compression!r}; expected PCM")
    if channels != 1:
        raise ValueError(f"Unsupported WAV channel count {channels}; expected mono")
    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width {sample_width}; expected PCM16")
    if not frames:
        raise ValueError(f"Audio file is empty: {path}")

    return sample_rate, frames


def _chunk_audio(pcm: bytes, *, sample_rate: int, chunk_ms: int) -> Iterable[bytes]:
    bytes_per_sample = 2
    frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
    bytes_per_chunk = frames_per_chunk * bytes_per_sample
    for offset in range(0, len(pcm), bytes_per_chunk):
        yield pcm[offset : offset + bytes_per_chunk]


async def _append_audio_chunk(connection, chunk: bytes) -> None:
    encoded = base64.b64encode(chunk).decode("ascii")
    await connection.input_audio_buffer.append(audio=encoded)


class SyncCredentialWrapper:
    """Wrap a synchronous Azure credential so the VoiceLive async SDK can use it.

    The VoiceLive SDK calls ``credential.get_token(...)`` *without* ``await``,
    so ``get_token`` must be a plain synchronous method.  Using the sync
    credential avoids Windows asyncio Proactor cleanup noise from async
    subprocess-based credentials (AzureCliCredential, etc.).
    """

    def __init__(self, credential) -> None:
        self._credential = credential

    def get_token(self, *scopes, **kwargs):
        return self._credential.get_token(*scopes, **kwargs)

    async def close(self) -> None:
        close = getattr(self._credential, "close", None)
        if callable(close):
            close()


async def run_voice_live_smoke_test(args: argparse.Namespace) -> None:
    from azure.ai.voicelive.aio import connect
    from azure.ai.voicelive.models import (
        AudioEchoCancellation,
        AudioNoiseReduction,
        AzureStandardVoice,
        InputAudioFormat,
        LlmInterimResponseConfig,
        Modality,
        OutputAudioFormat,
        RequestSession,
        ServerEventType,
        ServerVad,
    )
    from azure.identity import DefaultAzureCredential

    LOGGER.info("Starting Voice Live smoke test with endpoint=%s, agent_name=%s, project_name=%s, audio_file=%s",
        args.endpoint, args.agent_name, args.project_name, args.audio_file
    )

    sample_rate, pcm = _read_pcm16_wav(Path(args.audio_file))
    if sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"Audio file sample rate is {sample_rate}; expected {SAMPLE_RATE}. "
            "Regenerate the fixture to match the test configuration."
        )

    session_ready = asyncio.Event()
    user_transcript = ""
    response_transcript_parts: list[str] = []
    final_response_transcript = ""
    final_text_response = ""

    credential = SyncCredentialWrapper(DefaultAzureCredential())
    try:
        async with connect(
            endpoint=args.endpoint,
            credential=credential,
            agent_name=args.agent_name,
            project_name=args.project_name,
        ) as connection:
            session_config = RequestSession(
                modalities=[Modality.TEXT, Modality.AUDIO],
                voice=AzureStandardVoice(name=VOICE_NAME),
                input_audio_format=InputAudioFormat.PCM16,
                output_audio_format=OutputAudioFormat.PCM16,
                turn_detection=ServerVad(
                    threshold=VAD_THRESHOLD,
                    prefix_padding_ms=VAD_PREFIX_PADDING_MS,
                    silence_duration_ms=VAD_SILENCE_DURATION_MS,
                ),
                input_audio_echo_cancellation=AudioEchoCancellation(),
                input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
                interim_response=LlmInterimResponseConfig(latency_threshold_ms=INTERIM_LATENCY_MS),
            )

            LOGGER.info("Updating Voice Live session")
            await connection.session.update(session=session_config)

            async def send_audio() -> None:
                await asyncio.wait_for(session_ready.wait(), timeout=TIMEOUT_SECONDS)
                LOGGER.info("Streaming audio fixture: %s", args.audio_file)
                for chunk in _chunk_audio(pcm, sample_rate=sample_rate, chunk_ms=CHUNK_MS):
                    await _append_audio_chunk(connection, chunk)
                    await asyncio.sleep(CHUNK_MS / 1000)

                silence = b"\x00\x00" * int(sample_rate * TAIL_SILENCE_MS / 1000)
                for chunk in _chunk_audio(silence, sample_rate=sample_rate, chunk_ms=CHUNK_MS):
                    await _append_audio_chunk(connection, chunk)
                    await asyncio.sleep(CHUNK_MS / 1000)

                LOGGER.info("Finished streaming audio fixture")

            async def receive_events() -> None:
                nonlocal user_transcript, final_response_transcript, final_text_response
                async for event in connection:
                    event_type = event.type
                    LOGGER.debug("Voice Live event: %s", event_type)

                    if event_type == ServerEventType.SESSION_UPDATED:
                        session_id = getattr(getattr(event, "session", None), "id", "<unknown>")
                        LOGGER.info("Session updated: %s", session_id)
                        session_ready.set()

                    elif event_type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                        user_transcript = event.get("transcript", "")
                        LOGGER.info("User transcript: %s", user_transcript)

                    elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                        response_transcript_parts.append(event.delta)

                    elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                        final_response_transcript = event.get("transcript", "")
                        LOGGER.info("Response audio transcript: %s", final_response_transcript)

                    elif event_type == ServerEventType.RESPONSE_TEXT_DONE:
                        final_text_response = event.get("text", "")
                        LOGGER.info("Response text: %s", final_text_response)

                    elif event_type == ServerEventType.ERROR:
                        LOGGER.error("Voice Live error event: %s", event.error)
                        raise RuntimeError(f"Voice Live returned error: {event.error}")

                    elif event_type == ServerEventType.RESPONSE_DONE:
                        LOGGER.info("Response done")
                        return

            send_task = asyncio.create_task(send_audio())
            receive_task = asyncio.create_task(receive_events())

            try:
                await asyncio.wait_for(receive_task, timeout=TIMEOUT_SECONDS)
                await send_task
            finally:
                for task in (send_task, receive_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(send_task, receive_task, return_exceptions=True)
    finally:
        await credential.close()

    response_text = final_response_transcript or "".join(response_transcript_parts) or final_text_response
    LOGGER.info("Final user transcript: %s", user_transcript)
    LOGGER.info("Final agent response: %s", response_text)

    expected = EXPECTED_USER_TRANSCRIPT_CONTAINS.lower()
    if expected not in user_transcript.lower():
        raise AssertionError(
            f"Expected user transcript to contain {EXPECTED_USER_TRANSCRIPT_CONTAINS!r}, "
            f"got {user_transcript!r}"
        )

    if not response_text.strip():
        raise AssertionError("Voice Live completed but returned an empty response transcript")


def _derive_endpoint_from_env() -> str | None:
    """Extract scheme+host from AZURE_AI_PROJECT_ENDPOINT as the Voice Live endpoint."""
    project_ep = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not project_ep:
        return None
    from urllib.parse import urlparse
    parsed = urlparse(project_ep)
    return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else None


def _required_arg(value: str | None, name: str, env_var: str) -> str:
    if value:
        return value
    raise ValueError(f"Missing {name}. Pass {name} or set {env_var}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Headless Voice Live E2E smoke test")
    parser.add_argument("--endpoint", default=_derive_endpoint_from_env(), help="Voice Live endpoint")
    parser.add_argument("--agent-name", default=os.environ.get("AGENT_NAME"), help="Deployed hosted agent name")
    parser.add_argument("--project-name", default=os.environ.get("AZURE_AI_PROJECT_NAME"), help="Foundry project name")
    parser.add_argument("--audio-file", default=str(DEFAULT_AUDIO_FILE), help="PCM16 mono WAV file to stream")
    args = parser.parse_args()
    args.endpoint = _required_arg(args.endpoint, "--endpoint", "AZURE_AI_PROJECT_ENDPOINT")
    args.agent_name = _required_arg(args.agent_name, "--agent-name", "AGENT_NAME")
    args.project_name = _required_arg(args.project_name, "--project-name", "AZURE_AI_PROJECT_NAME")
    return args


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    try:
        asyncio.run(run_voice_live_smoke_test(args))
    except Exception:
        LOGGER.exception("Voice Live smoke test failed")
        return 1

    LOGGER.info("Voice Live smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())