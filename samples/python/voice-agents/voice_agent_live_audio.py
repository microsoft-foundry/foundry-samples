"""Pace a caller-provided WAV into Native GPT Live and save streamed reply audio.

Run: python voice_agent_live_audio.py [--store] [--listen-seconds 12]
Requires azure-ai-projects[voice]==2.11.0, azure-identity, python-dotenv.
Env: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_LIVE_MODEL (existing GPT Live
deployment), FOUNDRY_VOICE_AUDIO_INPUT_PATH (spoken PCM16 mono 24000-Hz WAV,
1 frame to 30 seconds). Optional FOUNDRY_VOICE_LIVE_OUTPUT_PATH: new reply WAV.
DefaultAzureCredential authenticates; no microphone, speakers, or binary fixture.

The bounded capture window is NOT a speech-completion signal and can cut off
long replies. --store opts into service persistence, reads transcript/merged
and first speech-item audio after session.closed, then deletes this run's
conversation/version.
Output WAV files contain real audio, not telemetry; keep and share them carefully.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import AsyncExitStack, contextmanager
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4
import wave

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.aio.operations import AsyncBetaLiveConnection
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_live_util import (
    FRAME_BYTES,
    LiveReceiveTimeout,
    SAMPLE_RATE,
    audio_settings,
    create_owned_agent,
    live_session,
    receive,
)


def has_audio(pcm: bytes) -> bool:
    return any(
        abs(int.from_bytes(pcm[i : i + 2], "little", signed=True)) > 256
        for i in range(0, len(pcm), 2)
    )


def read_pcm(path: Path) -> bytes:
    """Validate the entire short input before creating any service resource."""
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != SAMPLE_RATE
            or source.getcomptype() != "NONE"
        ):
            raise ValueError("Input must be uncompressed PCM16, mono, 24000-Hz WAV.")
        frames = source.getnframes()
        if not 0 < frames <= SAMPLE_RATE * 30:
            raise ValueError("Input WAV must contain between one frame and 30 seconds.")
        pcm = source.readframes(frames + 1)
        if len(pcm) != frames * 2 or not has_audio(pcm):
            raise ValueError("Input WAV is truncated or contains no audible speech.")
        return pcm


def decode_audio(event: Mapping[str, Any]) -> bytes:
    pcm = base64.b64decode(event["delta"], validate=True)
    if len(pcm) % 2:
        raise ValueError("Live returned an incomplete PCM16 sample.")
    return pcm


@contextmanager
def output_wav(path: Path) -> Iterator[wave.Wave_write]:
    """Never overwrite a caller's file or retain a failed partial recording."""
    raw = path.open("xb")
    success = False
    try:
        with raw, wave.open(raw, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            yield output
        success = True
    finally:
        if not success:
            path.unlink()


async def stream_audio(
    connection: AsyncBetaLiveConnection,
    pcm: bytes,
    output: wave.Wave_write,
    *,
    listen_seconds: float = 12,
    on_event: Callable[[AsyncBetaLiveConnection, Mapping[str, Any]], Awaitable[None]]
    | None = None,
) -> tuple[str, str, int]:
    """Keep sending silence after the WAV so Live's audio timeline keeps moving."""
    if not 1 <= listen_seconds <= 60:
        raise ValueError("listen_seconds must be between 1 and 60.")
    deadline = time.monotonic() + len(pcm) / (SAMPLE_RATE * 2) + listen_seconds
    input_text, output_text = [], []
    audio_bytes = 0
    audible = False

    async def send_audio() -> None:
        offset = 0
        while time.monotonic() < deadline:
            chunk = (
                pcm[offset : offset + FRAME_BYTES]
                if offset < len(pcm)
                else bytes(FRAME_BYTES)
            )
            offset += len(chunk)
            next_frame = time.monotonic() + len(chunk) / (SAMPLE_RATE * 2)
            await asyncio.wait_for(
                connection.session.input_audio.append(audio=chunk), timeout=10
            )
            await asyncio.sleep(max(0, next_frame - time.monotonic()))
        if offset < len(pcm):
            raise TimeoutError(
                "The capture window ended before all input audio was sent."
            )

    async def receive_audio() -> None:
        nonlocal audio_bytes, audible
        while time.monotonic() < deadline:
            try:
                event = await receive(connection, deadline)
            except LiveReceiveTimeout:
                # The pending socket read is reused when live_session requests close.
                return
            if event.get("type") == "session.closed":
                raise RuntimeError("Live closed before the capture window ended.")
            if isinstance(event, models.LiveOutputAudioDelta):
                chunk = decode_audio(event)
                output.writeframesraw(chunk)
                audio_bytes += len(chunk)
                audible = audible or has_audio(chunk)
            elif isinstance(event, models.LiveServerEventLiveInputTranscriptDelta):
                input_text.append(event.delta)
            elif isinstance(event, models.LiveServerEventLiveOutputTranscriptDelta):
                output_text.append(event.delta)
            if on_event is not None:
                await on_event(connection, event)
            elif isinstance(event, models.LiveServerEventLiveDelegationCreated):
                raise RuntimeError(
                    "Unexpected delegation; use voice_agent_live_delegation.py for backend work."
                )

    tasks = [asyncio.create_task(send_audio()), asyncio.create_task(receive_audio())]
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks), timeout=max(0, deadline - time.monotonic()) + 5
        )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not audio_bytes or not audible:
        raise RuntimeError(
            "The capture window contained no non-silent Live reply audio."
        )
    return "".join(input_text), "".join(output_text), audio_bytes


async def main(store: bool = False, listen_seconds: float = 12) -> None:
    if not 1 <= listen_seconds <= 60:
        raise ValueError("listen_seconds must be between 1 and 60.")
    load_dotenv()
    pcm = read_pcm(Path(os.environ["FOUNDRY_VOICE_AUDIO_INPUT_PATH"]))
    path = Path(
        os.environ.get("FOUNDRY_VOICE_LIVE_OUTPUT_PATH")
        or f"voice-live-reply-{uuid4().hex[:8]}.wav"
    )
    definition = models.VoiceAgentLiveDefinition(
        model_type=models.VoiceModelType.SELF_DEPLOYED,
        model=os.environ["FOUNDRY_VOICE_LIVE_MODEL"],
        instructions="Briefly answer the user's spoken question yourself. Do not delegate; use one short sentence.",
        audio=audio_settings(),
        store=store,
    )
    with output_wav(path) as output:
        async with (
            DefaultAzureCredential(process_timeout=60) as credential,
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=credential,
                allow_preview=True,
            ) as project,
            AsyncExitStack() as cleanup,
        ):
            agent = await create_owned_agent(project, cleanup, "audio", definition)
            async with live_session(project, cleanup, agent, store=store) as (
                connection,
                started,
            ):
                user_text, agent_text, count = await stream_audio(
                    connection, pcm, output, listen_seconds=listen_seconds
                )
            if store:
                from voice_agent_live_readback import readback

                if not started.conversation_id:
                    raise RuntimeError(
                        "Stored Live session omitted its conversation ID."
                    )
                merged_path = path.with_name(f"{path.stem}-merged.wav")
                await readback(
                    project,
                    agent.name,
                    started.conversation_id,
                    merged_path,
                    credential=credential,
                )
    if user_text:
        print(f"Input transcript: {user_text}")
    if agent_text:
        print(f"Output transcript: {agent_text}")
    print(
        f"Captured {count} reply PCM16 bytes in {path}; capture-window end does not prove speech completion."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        action="store_true",
        help="Persist, read back, and delete this run's Live conversation.",
    )
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=12,
        help="Capture window after input ends (1-60 seconds).",
    )
    options = parser.parse_args()
    asyncio.run(main(options.store, options.listen_seconds))
