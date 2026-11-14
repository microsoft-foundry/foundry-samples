"""
DESCRIPTION:
    End-to-end hands-free, bidirectional voice conversation using the
    ``client.voice_agents.realtime`` namespace.
    This mirrors the ergonomics of the OpenAI Python realtime client.

      1. Create a voice agent with conversation persistence enabled
         (`store=True`) so the conversation can be read back afterward.
      2. Stream live mic audio and let the agent's server-side VAD detect your
         turns: your speech is transcribed, the agent replies through the
         speakers, and talking over it barges in.
      3. Fetch the persisted conversation back by id.
      4. Delete the agent created for this sample.

    Capture and playback use non-blocking pyaudio callbacks; reply audio is
    sequence-numbered so a barge-in can skip whatever is still queued. The
    agent owns turn detection and noise suppression server-side. Use a headset
    to avoid echo.

    Mic audio is sent as base64 PCM16; the reply arrives as typed
    ``response.output_audio.*`` events, decoded to PCM16, mono, 24 kHz.
    Requires ``aiohttp`` and ``pyaudio``.

      pip install "azure-ai-projects[voice]==2.11.0" azure-identity python-dotenv pyaudio

USAGE:
    python voice_agent_realtime_audio_conversation_async.py
    python voice_agent_realtime_audio_conversation_async.py --audio-file question.wav --output-audio reply.wav

    --audio-file is a bounded, headless turn using a supplied PCM16 mono 24 kHz
    WAV. It never opens a microphone or speaker and does not require PyAudio.

    Environment variables:
    1) FOUNDRY_PROJECT_ENDPOINT (required) - Foundry project endpoint:
       https://<account>.services.ai.azure.com/api/projects/<project>
    2) FOUNDRY_VOICE_AGENT_MODEL - Optional. The realtime model deployment name.
       Defaults to "gpt-realtime".
    3) FOUNDRY_VOICE_AGENT_NAME - Optional unused name. Otherwise a unique
       sample-owned name is generated.

    Runs until you press Ctrl-C. Authenticates with DefaultAzureCredential, so
    sign in first (e.g. `az login`).
"""

import argparse
import asyncio
import concurrent.futures
import contextlib
import json
import os
import queue
import threading
import wave
from collections import deque
from pathlib import Path
from typing import Any, Final, Optional

from dotenv import load_dotenv
from azure.core.exceptions import HttpResponseError
from azure.identity.aio import DefaultAzureCredential

from azure.ai.projects.aio.operations import AsyncRealtimeConnection
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
    RealtimeServerEventConversationItemInputAudioTranscriptionFailed,
    RealtimeServerEventInputAudioBufferSpeechStarted,
    RealtimeServerEventInputAudioBufferSpeechStopped,
    RealtimeServerEventResponseAudioDelta,
    RealtimeServerEventResponseAudioTranscriptDone,
    RealtimeServerEventResponseCreated,
    RealtimeServerEventResponseDone,
    RealtimeServerEventSessionCreated,
    RealtimeServerEventError,
    RealtimeAudioFormatsAudioPcm,
    VoiceAgentAudioConfig,
    VoiceAgentAudioInputConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentDefinition,
    VoiceAgentInputTranscription,
    VoiceAgentServerVadTurnDetection,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)

from voice_agent_util import (
    format_conversation_item,
    require_new_agent_async,
    safe_print,
    sample_agent_name,
    wait_for_conversation_async,
)

load_dotenv()


# Audio is streamed both ways as PCM16, mono, 24 kHz.
_SAMPLE_RATE: Final = 24000

# pyaudio callback buffer size (~50 ms of PCM16 audio per callback).
_CHUNK_SAMPLES: Final = 1200

try:
    import pyaudio  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional in file mode
    pyaudio: Any = None  # type: ignore[no-redef]


def read_pcm_wav(path: Path) -> bytes:
    """Read a nonempty PCM16, mono, 24 kHz WAV without touching an audio device."""
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        ) != (1, 2, _SAMPLE_RATE, "NONE"):
            raise ValueError("Input must be uncompressed PCM16, mono, 24000 Hz WAV.")
        pcm = source.readframes(source.getnframes())
    if not pcm or len(pcm) % 2:
        raise ValueError("Input WAV must contain complete PCM16 samples.")
    return pcm


async def run_file_conversation(
    client: AIProjectClient,
    agent_name: str,
    audio_file: Path,
    output_audio: Path,
    *,
    use_vad: bool = False,
    timeout: float = 60,
) -> dict[str, Any]:
    """Stream a WAV to an existing Realtime voice frontend and save its response.

    The caller owns the client, agent/version, and persisted conversation. This
    helper creates/deletes no agents and closes only its own WebSocket and files.
    Input and output are PCM16 mono 24 kHz; the output path must not exist.
    VAD mode sends real-time chunks followed by silence and lets the service
    commit/create the turn. Use it for Azure Speech with Azure semantic VAD.
    Manual mode explicitly commits and creates the turn; the existing frontend
    must already have VAD disabled and a compatible transcription provider.
    Keep receiving while all input and EOF silence are sent. Completion requires
    the latest turn's completed response, a non-silent final audio item, and input
    transcription. A VAD ``turn_detected`` cancellation must match newer speech.
    The voice frontend can report that interruption as ``client_cancelled``
    while input is streaming; other unsuccessful responses still fail.
    """
    pcm = read_pcm_wav(audio_file)
    if output_audio.exists():
        raise FileExistsError(f"Refusing to overwrite {output_audio}.")
    result: dict[str, Any] = {
        "input_bytes": len(pcm),
        "audio_bytes": 0,
        "audio_chunks": 0,
        "speech_started": 0,
        "speech_stopped": 0,
        "input_transcript_characters": 0,
        "response_statuses": [],
        "response_status_details": [],
        "response_transcripts": [],
        "response_metadata": [],
        "audio_item_bytes": {},
        "transcript_item_ids": [],
        "final_response_id": None,
        "conversation_id": None,
    }
    async with client.voice_agents.realtime.connect(agent_name=agent_name) as conn:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            event = await asyncio.wait_for(
                conn.recv(), deadline - asyncio.get_running_loop().time()
            )
            if isinstance(event, RealtimeServerEventError):
                raise RuntimeError(event.error.message)
            if isinstance(event, RealtimeServerEventSessionCreated):
                result["conversation_id"] = event.conversation_id
                break

        async def send_audio() -> None:
            for offset in range(0, len(pcm), _CHUNK_SAMPLES * 2):
                chunk = pcm[offset : offset + _CHUNK_SAMPLES * 2]
                await conn.input_audio_buffer.append(audio=chunk)
                if use_vad:
                    await asyncio.sleep(len(chunk) / 2 / _SAMPLE_RATE)
            if use_vad:
                # This is explicit end-of-file silence, not a simulated microphone.
                for _ in range(40):
                    await conn.input_audio_buffer.append(
                        audio=bytes(_CHUNK_SAMPLES * 2)
                    )
                    await asyncio.sleep(_CHUNK_SAMPLES / _SAMPLE_RATE)
            else:
                await conn.input_audio_buffer.commit()
                await conn.response.create()

        sender = asyncio.create_task(send_audio())
        receiver = asyncio.create_task(conn.recv())
        try:
            with output_audio.open("xb") as raw, wave.open(raw, "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(_SAMPLE_RATE)
                speech_turn = 0
                response_turns: dict[str, int] = {}
                audio_items: dict[str, set[str]] = {}
                transcript_items: dict[str, set[str]] = {}
                started_items: set[str] = set()
                stopped_items: set[str] = set()
                transcribed_items: set[str] = set()
                streaming_interrupts: set[str] = set()
                latest_response_id = None
                completed_response_id = None
                final_item_id = None
                while True:
                    if sender.done():
                        sender.result()
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError(
                            "Timed out waiting for the final voice response."
                        )
                    pending: set[asyncio.Task[object]] = {receiver}
                    if not sender.done():
                        pending.add(sender)
                    done, _ = await asyncio.wait(
                        pending,
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        raise TimeoutError(
                            "Timed out waiting for the final voice response."
                        )
                    if sender in done:
                        sender.result()
                    event = receiver.result() if receiver in done else None
                    if receiver in done:
                        receiver = asyncio.create_task(conn.recv())
                    if isinstance(
                        event,
                        (
                            RealtimeServerEventError,
                            RealtimeServerEventConversationItemInputAudioTranscriptionFailed,
                        ),
                    ):
                        raise RuntimeError(event.error.message)
                    if isinstance(
                        event, RealtimeServerEventInputAudioBufferSpeechStarted
                    ):
                        if (
                            use_vad
                            and not sender.done()
                            and latest_response_id is not None
                            and completed_response_id is None
                        ):
                            streaming_interrupts.add(latest_response_id)
                        result["speech_started"] += 1
                        speech_turn += 1
                        started_items.add(event.item_id)
                        completed_response_id = None
                    elif isinstance(
                        event, RealtimeServerEventInputAudioBufferSpeechStopped
                    ):
                        result["speech_stopped"] += 1
                        stopped_items.add(event.item_id)
                    elif isinstance(
                        event,
                        RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
                    ):
                        result["input_transcript_characters"] += len(
                            event.transcript.strip()
                        )
                        transcribed_items.add(event.item_id)
                    elif isinstance(event, RealtimeServerEventResponseCreated):
                        response_id = event.response.id
                        if not response_id:
                            raise RuntimeError(
                                "The voice response omitted its response ID."
                            )
                        latest_response_id = response_id
                        response_turns[response_id] = speech_turn
                        completed_response_id = None
                    elif isinstance(event, RealtimeServerEventResponseAudioDelta):
                        if not event.delta or len(event.delta) % 2:
                            raise ValueError("Invalid PCM16 response chunk.")
                        target.writeframes(event.delta)
                        result["audio_bytes"] += len(event.delta)
                        result["audio_chunks"] += 1
                        result["audio_item_bytes"][event.item_id] = result[
                            "audio_item_bytes"
                        ].get(event.item_id, 0) + len(event.delta)
                        if any(event.delta):
                            audio_items.setdefault(event.response_id, set()).add(
                                event.item_id
                            )
                    elif isinstance(
                        event, RealtimeServerEventResponseAudioTranscriptDone
                    ):
                        result["response_transcripts"].append(event.transcript)
                        result["transcript_item_ids"].append(event.item_id)
                        if event.transcript.strip():
                            transcript_items.setdefault(event.response_id, set()).add(
                                event.item_id
                            )
                    elif isinstance(event, RealtimeServerEventResponseDone):
                        response_id = event.response.id
                        if not response_id:
                            raise RuntimeError(
                                "The voice response omitted its response ID."
                            )
                        result["response_statuses"].append(event.response.status)
                        result["response_metadata"].append(
                            dict(event.response.metadata or {})
                        )
                        details = event.response.status_details
                        result["response_status_details"].append(
                            details.as_dict() if details is not None else None
                        )
                        expected_barge_in = (
                            use_vad
                            and event.response.status == "cancelled"
                            and details is not None
                            and (
                                details.reason == "turn_detected"
                                or (
                                    details.reason == "client_cancelled"
                                    and response_id in streaming_interrupts
                                )
                            )
                            and response_turns.get(response_id, speech_turn)
                            < speech_turn
                        )
                        if (
                            event.response.status != "completed"
                            and not expected_barge_in
                        ):
                            raise RuntimeError(
                                f"Voice response ended with status {event.response.status}: "
                                f"{result['response_status_details'][-1]}."
                            )
                        if (
                            event.response.status == "completed"
                            and response_id == latest_response_id
                            and response_turns.get(response_id) == speech_turn
                        ):
                            completed_response_id = response_id
                            final_item_id = (
                                event.response.output[-1].get("id")
                                if event.response.output
                                else None
                            )
                    if (
                        sender.done()
                        and completed_response_id is not None
                        and completed_response_id == latest_response_id
                        and response_turns.get(completed_response_id) == speech_turn
                        and final_item_id
                        in audio_items.get(completed_response_id, set())
                        and final_item_id
                        in transcript_items.get(completed_response_id, set())
                        and result["input_transcript_characters"] > 0
                        and (
                            not use_vad
                            or (
                                started_items
                                and started_items <= stopped_items
                                and started_items <= transcribed_items
                            )
                        )
                    ):
                        # Drain already queued events before accepting an EOF candidate.
                        await asyncio.sleep(0)
                        if not receiver.done():
                            result["final_response_id"] = completed_response_id
                            break
                if use_vad and not (
                    result["speech_started"] and result["speech_stopped"]
                ):
                    raise RuntimeError("The service did not detect the supplied turn.")
        finally:
            for task in (sender, receiver):
                task.cancel()
            for task in (sender, receiver):
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    print(
        f"File turn: input_bytes={result['input_bytes']}, "
        f"audio_bytes={result['audio_bytes']}, "
        f"audio_chunks={result['audio_chunks']}, "
        f"response_statuses={result['response_statuses']}"
    )
    return result


def _format_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    :param num_bytes: The size in bytes.
    :type num_bytes: int
    :return: A string like "12345 bytes (12.1 KB)" or "2097152 bytes (2.00 MB)".
    :rtype: str
    """
    if num_bytes < 1024:
        return f"{num_bytes} bytes"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes} bytes ({num_bytes / 1024:.1f} KB)"
    return f"{num_bytes} bytes ({num_bytes / (1024 * 1024):.2f} MB)"


class _AudioProcessor:  # pylint: disable=too-many-instance-attributes
    """Real-time mic capture and speaker playback via non-blocking pyaudio callbacks.

    * Capture appends each raw PCM16 frame to the input buffer (the realtime
      client base64-encodes it).
    * Playback pulls sequence-numbered PCM16 from a queue, always returning the
      exact sample count pyaudio asked for (a wrong size corrupts audio).
    * ``skip_pending_audio`` bumps a base sequence number so audio queued before
      a barge-in is dropped, stopping playback the instant the user speaks.
    """

    def __init__(self, connection: "AsyncRealtimeConnection") -> None:
        self._conn = connection
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio = pyaudio.PyAudio()

        # Playback with sequence numbers for interrupt handling.
        self._playback_queue: queue.Queue[
            tuple[int, Optional[bytes], Optional[str], int]
        ] = queue.Queue()
        self._playback_base = 0
        self._next_seq = 0
        self._output_bytes = 0
        self._playback_lock = threading.Lock()
        self._scheduled: deque[tuple[float, str, int, int]] = deque()
        self._heard: dict[tuple[str, int], int] = {}
        self._received: dict[tuple[str, int], int] = {}
        self._last_item: Optional[tuple[str, int]] = None

        # Bounds capture backpressure to a single in-flight send (see start_capture).
        self._pending_send: "Optional[concurrent.futures.Future[None]]" = None
        self._dropped_frames = 0
        # Only counts bytes actually handed to input_audio_buffer.append() -- frames dropped
        # above due to backpressure are never sent, so they must not be counted here.
        self._input_bytes = 0

        self._input_stream = None
        self._output_stream = None

    # -- capture -----------------------------------------------------------

    def start_capture(self) -> None:
        """Start streaming microphone audio to the service via a callback."""
        if self._input_stream is not None:
            return
        self._loop = asyncio.get_running_loop()

        def _capture_callback(in_data, _frame_count, _time_info, _status):
            # Runs on a pyaudio thread: hand the frame to the event loop to append. Each call
            # schedules a coroutine on the loop via a thread-safe handoff; if sending falls
            # behind real-time capture (for example, network backpressure on the WebSocket),
            # unconditionally scheduling a new one every callback would let pending sends
            # accumulate without bound. Instead, only keep at most one in flight and drop
            # (skip sending) this frame if the previous send hasn't completed yet.
            assert self._loop is not None
            if self._pending_send is not None and not self._pending_send.done():
                self._dropped_frames += 1
                return (None, pyaudio.paContinue)
            self._input_bytes += len(in_data)
            self._pending_send = asyncio.run_coroutine_threadsafe(
                self._conn.input_audio_buffer.append(audio=in_data), self._loop
            )
            return (None, pyaudio.paContinue)

        self._input_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=_SAMPLE_RATE,
            input=True,
            frames_per_buffer=_CHUNK_SAMPLES,
            stream_callback=_capture_callback,
        )

    # -- playback ------------------------------------------------------------

    def start_playback(self) -> None:
        """Initialize the speaker playback callback."""
        if self._output_stream is not None:
            return
        remaining = b""
        # The sequence number the currently-buffered `remaining` bytes were dequeued from, so a
        # barge-in that lands *between* callback invocations can still discard them below.
        remaining_seq = -1
        remaining_item: Optional[str] = None
        remaining_content = 0

        def _playback_callback(_in_data, frame_count, _time_info, _status):
            nonlocal remaining, remaining_seq, remaining_item, remaining_content
            if remaining and remaining_seq < self._playback_base:
                remaining = (
                    b""  # a barge-in advanced the base since this chunk was dequeued
                )

            wanted = frame_count * pyaudio.get_sample_size(pyaudio.paInt16)
            out = remaining[:wanted]
            remaining = remaining[wanted:]
            scheduled = []
            if out and remaining_item is not None:
                scheduled.append((0, remaining_item, remaining_content, len(out)))

            while len(out) < wanted:
                try:
                    (
                        seq,
                        data,
                        item_id,
                        content_index,
                    ) = self._playback_queue.get_nowait()
                except queue.Empty:
                    out = out + bytes(wanted - len(out))  # pad with silence
                    continue
                if not data:
                    # end-of-stream marker: pad up to the exact frame size pyaudio asked for
                    # instead of returning a short buffer, which would corrupt playback on close.
                    out = out + bytes(wanted - len(out))
                    break
                if seq < self._playback_base:
                    remaining = b""  # skipped by a barge-in
                    continue
                take = wanted - len(out)
                if item_id is not None:
                    scheduled.append(
                        (len(out), item_id, content_index, min(take, len(data)))
                    )
                out = out + data[:take]
                remaining = data[take:]
                remaining_seq = seq
                remaining_item = item_id
                remaining_content = content_index

            with self._playback_lock:
                self._settle_playback(_time_info["current_time"])
                for offset, item_id, content_index, size in scheduled:
                    self._scheduled.append(
                        (
                            _time_info["output_buffer_dac_time"]
                            + offset / 2 / _SAMPLE_RATE,
                            item_id,
                            content_index,
                            size,
                        )
                    )

            return (out, pyaudio.paContinue)

        self._output_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=_SAMPLE_RATE,
            output=True,
            frames_per_buffer=_CHUNK_SAMPLES,
            stream_callback=_playback_callback,
        )

    def _next_seq_num(self) -> int:
        seq = self._next_seq
        self._next_seq += 1
        return seq

    def queue_audio(
        self,
        pcm: bytes,
        *,
        item_id: Optional[str] = None,
        content_index: int = 0,
        play: bool = True,
    ) -> None:
        """Queue one decoded PCM16 chunk of the agent's reply for playback.

        :param pcm: Decoded PCM16 audio bytes.
        :type pcm: bytes
        """
        self._output_bytes += len(pcm)
        if not play:
            return
        if item_id is not None:
            with self._playback_lock:
                key = (item_id, content_index)
                self._received[key] = self._received.get(key, 0) + len(pcm)
                self._last_item = key
        self._playback_queue.put((self._next_seq_num(), pcm, item_id, content_index))

    def _settle_playback(self, now: float) -> None:
        while self._scheduled:
            start, item_id, content_index, size = self._scheduled[0]
            if start + size / 2 / _SAMPLE_RATE > now:
                break
            self._scheduled.popleft()
            key = (item_id, content_index)
            self._heard[key] = self._heard.get(key, 0) + size

    def interrupt_playback(self) -> Optional[tuple[str, int, int]]:
        """Stop queued audio and return the DAC-played position, not received duration."""
        self.skip_pending_audio()
        with self._playback_lock:
            assert self._output_stream is not None
            now = self._output_stream.get_time()
            self._settle_playback(now)
            key = self._last_item
            if key is None:
                return None
            heard = self._heard.get(key, 0)
            for start, item_id, content_index, size in self._scheduled:
                if (item_id, content_index) == key:
                    heard += min(size, max(0, int((now - start) * _SAMPLE_RATE)) * 2)
            self._scheduled.clear()
            if heard >= self._received[key]:
                return None
            return key[0], key[1], heard * 1000 // (2 * _SAMPLE_RATE)

    def skip_pending_audio(self) -> None:
        """Drop audio still queued for playback (used on barge-in)."""
        self._playback_base = self._next_seq_num()

    def shutdown(self) -> None:
        """Stop capture and playback and release the audio device."""
        if self._input_stream is not None:
            self._input_stream.stop_stream()
            self._input_stream.close()
            self._input_stream = None
            if self._dropped_frames:
                print(
                    f"(dropped {self._dropped_frames} mic frame(s) while a send was still in flight)"
                )
        if self._output_stream is not None:
            self.skip_pending_audio()
            self._playback_queue.put((self._next_seq_num(), None, None, 0))
            self._output_stream.stop_stream()
            self._output_stream.close()
            self._output_stream = None
        self._audio.terminate()

    @property
    def input_bytes_sent(self) -> int:
        """Total raw PCM16 mic-audio bytes actually sent to the service (excludes dropped frames).

        :rtype: int
        """
        return self._input_bytes

    @property
    def output_bytes_received(self) -> int:
        """Total decoded PCM16 reply-audio bytes received from the service.

        :rtype: int
        """
        return self._output_bytes

    @property
    def input_seconds(self) -> float:
        """Total mic audio sent, in seconds (PCM16 = 2 bytes/sample).

        :rtype: float
        """
        return self._input_bytes / 2 / _SAMPLE_RATE

    @property
    def seconds(self) -> float:
        """Total reply audio received, in seconds (PCM16 = 2 bytes/sample).

        :rtype: float
        """
        return self._output_bytes / 2 / _SAMPLE_RATE


async def _run_audio_conversation(
    client: AIProjectClient, agent_name: str
) -> Optional[str]:
    """Hold a live, hands-free conversation with barge-in.

    :param client: The Foundry project client.
    :param agent_name: The existing voice agent name.
    :type client: ~azure.ai.projects.aio.AIProjectClient
    :type agent_name: str
    :return: The persisted conversation id, if one is created.
    :rtype: str or None
    """
    if pyaudio is None:
        raise ImportError("This sample needs PyAudio: pip install pyaudio")

    conversation_id: Optional[str] = None
    response_active = False
    active_response_id: Optional[str] = None
    cancelled_responses: set[str] = set()

    # Open the realtime session on the voice agent's dedicated route.
    async with client.voice_agents.realtime.connect(agent_name=agent_name) as conn:
        # A voice agent owns its model, instructions, voice, turn detection, and
        # noise suppression server-side, so this client sends no ``session.update``.
        ap = _AudioProcessor(conn)
        try:
            ap.start_playback()
            ap.start_capture()
            print("Speak now -- the agent replies after you pause.")
            print(
                "(talk over the agent to interrupt it; press Ctrl-C to end the session)"
            )
            async for event in conn:
                if isinstance(event, RealtimeServerEventSessionCreated):
                    # The persisted conversation id (only present when conversation
                    # persistence is enabled) is set here, not on response.done.
                    conversation_id = event.conversation_id or conversation_id
                elif isinstance(
                    event, RealtimeServerEventInputAudioBufferSpeechStarted
                ):
                    # speech_started fires for every user turn, including the very first one,
                    # when no response is active yet. Always drop whatever reply audio is still
                    # queued locally -- the speaker can lag well behind the server finishing
                    # generation, so buffered audio can outlive response_active going false and
                    # must still be cleared here. Only cancel the *server-side* response (a
                    # separate RPC) and announce the barge-in when a response is actually in
                    # flight; canceling with none active is a service error.
                    position = ap.interrupt_playback()
                    if response_active:
                        await conn.response.cancel()
                        if active_response_id is not None:
                            cancelled_responses.add(active_response_id)
                        response_active = False
                        print("(listening...)")
                    if position is not None:
                        item_id, content_index, heard_ms = position
                        await conn.conversation.item.truncate(
                            item_id=item_id,
                            content_index=content_index,
                            audio_end_ms=heard_ms,
                        )
                elif isinstance(
                    event,
                    RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
                ):
                    print(f"You:  {event.transcript.strip()}")
                elif isinstance(event, RealtimeServerEventError):
                    raise RuntimeError(event.error.message)
                elif isinstance(event, RealtimeServerEventResponseCreated):
                    response_active = True
                    active_response_id = event.response.id
                elif isinstance(event, RealtimeServerEventResponseAudioDelta):
                    # Each delta is a decoded PCM16 chunk; queue it.
                    ap.queue_audio(
                        event.delta,
                        item_id=event.item_id,
                        content_index=event.content_index,
                        play=event.response_id not in cancelled_responses,
                    )
                elif isinstance(event, RealtimeServerEventResponseAudioTranscriptDone):
                    safe_print(f"Agent: {event.transcript}")
                elif isinstance(event, RealtimeServerEventResponseDone):
                    response_active = False
                    if event.response.status not in ("completed", "cancelled"):
                        raise RuntimeError(
                            f"Voice response ended with status {event.response.status}."
                        )
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Ctrl-C ends the session; read back whatever was persisted so far.
            print("\n(ending session...)")
        finally:
            input_bytes = ap.input_bytes_sent
            output_bytes = ap.output_bytes_received
            print(f"(received {ap.seconds:.2f}s of reply audio this session)")
            print(
                f"Input audio (mic -> service): format=PCM16, sample_rate={_SAMPLE_RATE} Hz, channels=1, "
                f"duration={ap.input_seconds:.2f}s, size={_format_size(input_bytes)}"
            )
            print(
                f"Output audio (service -> speakers): format=PCM16, sample_rate={_SAMPLE_RATE} Hz, channels=1, "
                f"duration={ap.seconds:.2f}s, size={_format_size(output_bytes)}"
            )
            print(
                f"Total audio transferred: size={_format_size(input_bytes + output_bytes)}"
            )
            ap.shutdown()

    return conversation_id


async def _read_conversation(
    client: AIProjectClient, agent_name: str, conversation_id: str
) -> None:
    """Read the persisted conversation back over the read-only conversation API.

    :param client: The Foundry project client.
    :param agent_name: The voice agent name.
    :param conversation_id: The persisted conversation id.
    :type client: ~azure.ai.projects.aio.AIProjectClient
    :type agent_name: str
    :type conversation_id: str
    """
    conversations = client.voice_agents.conversations

    conversation = await wait_for_conversation_async(
        client, agent_name, conversation_id
    )
    print(
        f"Conversation {conversation.id}: status={conversation.status}, created_at={conversation.created_at}"
    )

    print("Items (transcript):")
    async for item in conversations.list_items(
        agent_name, conversation_id, order="asc"
    ):
        safe_print(f"  - {format_conversation_item(item)}")


async def audio_conversation(
    audio_file: Optional[Path] = None, output_audio: Optional[Path] = None
) -> None:
    if audio_file is None and output_audio is not None:
        raise ValueError("--output-audio requires --audio-file.")
    if audio_file is None and pyaudio is None:
        raise ImportError("This sample needs PyAudio: pip install pyaudio")
    if audio_file is not None:
        read_pcm_wav(audio_file)
        if output_audio is None:
            raise ValueError("--audio-file requires --output-audio.")
        if output_audio.exists():
            raise FileExistsError(f"Refusing to overwrite {output_audio}.")
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-realtime-audio-conversation-agent-async")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        await require_new_agent_async(project_client, agent_name)
        created_version = None
        try:
            # 1) Create a voice agent with conversation persistence enabled (`store=True`) so the
            #    session's conversation can be fetched back by id afterward.
            definition = VoiceAgentDefinition(
                model_type=VoiceModelType.MANAGED,
                model=model,
                instructions="You are a friendly voice assistant. Keep replies short and natural.",
                audio=VoiceAgentAudioConfig(
                    input=VoiceAgentAudioInputConfig(
                        format=RealtimeAudioFormatsAudioPcm(rate=_SAMPLE_RATE),
                        turn_detection=(
                            VoiceAgentServerVadTurnDetection(
                                create_response=True, interrupt_response=False
                            )
                            if audio_file is None
                            else None
                        ),
                        transcription=VoiceAgentInputTranscription(
                            model="gpt-4o-transcribe", language="en"
                        ),
                    ),
                    output=VoiceAgentAudioOutputConfig(
                        voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
                    ),
                ),
                output_modalities=[VoiceOutputModality.AUDIO],
                store=True,
            )
            if audio_file is not None:
                assert definition.audio is not None
                assert definition.audio.input is not None
                definition.audio.input["turn_detection"] = None
            created_version = await project_client.agents.create_version(
                agent_name=agent_name,
                definition=definition,
            )

            # 2) Hold a live microphone conversation with the freshly created agent.
            print(f"Starting realtime session with agent: {agent_name}")
            if audio_file is None:
                conversation_id = await _run_audio_conversation(
                    project_client, agent_name
                )
            else:
                assert output_audio is not None
                result = await run_file_conversation(
                    project_client, agent_name, audio_file, output_audio
                )
                conversation_id = result["conversation_id"]
                print(
                    json.dumps(
                        {k: v for k, v in result.items() if k != "response_transcripts"}
                    )
                )

            # 3) Fetch the persisted conversation back by id.
            if conversation_id:
                print(f"Reading persisted conversation {conversation_id!r}...")
                try:
                    await _read_conversation(
                        project_client, agent_name, conversation_id
                    )
                except HttpResponseError as e:
                    print(f"Could not read conversation: {e.status_code} {e.reason}")
                    raise
                # To fetch this session's audio afterward, use
                # `project_client.voice_agents.conversations`:
                #   - get_audio(agent_name, conversation_id) for the merged
                #     whole-call stereo recording's metadata, then
                #     download_audio(agent_name, conversation_id) to stream
                #     the WAV bytes.
                #   - get_audio_item(agent_name, conversation_id, item_id) for a
                #     single turn's audio metadata, then
                #     download_audio_item(agent_name, conversation_id, item_id)
                #     to stream that turn's bytes.
                # See voice_agent_read_conversation_audio.py for a full example.
            else:
                print("No conversation id was returned; nothing to read.")
        except HttpResponseError as e:
            print(f"Service responded with an error: {e.status_code} {e.reason}")
            raise
        finally:
            # 4) Clean up the agent created for this sample.
            if created_version is not None:
                await project_client.agents.delete_version(
                    agent_name=agent_name, agent_version=created_version.version
                )
                print(f"Deleted voice agent version: {created_version.version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-file", type=Path)
    parser.add_argument("--output-audio", type=Path)
    args = parser.parse_args()
    if (args.audio_file is None) != (args.output_audio is None):
        parser.error("--audio-file and --output-audio must be supplied together.")
    try:
        asyncio.run(audio_conversation(args.audio_file, args.output_audio))
    except KeyboardInterrupt:
        print("\nInterrupted.")
