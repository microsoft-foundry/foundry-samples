"""Audio devices, PCM frames, and WAV files only; no agents, events, or networking."""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
import wave
from collections.abc import AsyncIterator
from pathlib import Path

# Shared mono PCM16 capture/streaming format: Audio validates WAVs and paces
# frames using these constants.
# gpt_live.response_delegation and gpt_live.prompt_agent_delegation use RATE for audio setup.
# realtime_stt.sample references RATE, FRAMES, and FRAME_BYTES for input setup and trailing silence.
RATE = 24000  # Sample rate in Hz used for both microphone capture and WAV validation.
FRAMES = 480  # Samples per frame; sends 20 ms of mono PCM16 at RATE.
FRAME_BYTES = FRAMES * 2  # Byte length used to pad frames and generate silence.


class AudioError(Exception):
    """An audio device, format, or buffering failure."""


class Audio:
    """Capture/play PCM off the asyncio loop; callers own all protocol handling."""

    def __init__(
        self,
        *,
        input_wav: Path | None = None,
        input_device: int | str | None = None,
        output_device: int | str | None = None,
        no_playback: bool = False,
        tail_seconds: float = 12,
        save_audio: Path | None = None,
    ):
        self.input_wav = input_wav
        self.input_device = input_device
        self.output_device = output_device
        self.no_playback = no_playback
        self.tail_seconds = tail_seconds
        self.save_audio = save_audio
        self.microphone = queue.Queue(maxsize=100)  # 2 seconds; overflow fails visibly.
        self.output = bytearray()
        self.lock = threading.Lock()
        self.input_stream = self.output_stream = self.wav = self.wav_file = None
        self.input_error = None
        self.sd = None

    def __enter__(self):
        if sys.byteorder != "little":
            raise AudioError("These demos require a little-endian PCM16 host.")
        if self.input_wav:
            with wave.open(str(self.input_wav), "rb") as source:
                if (
                    source.getnchannels(),
                    source.getsampwidth(),
                    source.getframerate(),
                    source.getcomptype(),
                ) != (1, 2, RATE, "NONE"):
                    raise AudioError(
                        "Input WAV must be uncompressed mono PCM16 at 24000 Hz."
                    )
        if not self.input_wav or not self.no_playback:
            try:
                import sounddevice as sd
            except (ImportError, OSError) as exc:
                raise AudioError(
                    "Install requirements.txt and PortAudio to use microphone/speaker devices."
                ) from exc
            self.sd = sd
            try:
                if not self.input_wav:
                    sd.check_input_settings(
                        device=self.input_device,
                        channels=1,
                        dtype="int16",
                        samplerate=RATE,
                    )
                if not self.no_playback:
                    sd.check_output_settings(
                        device=self.output_device,
                        channels=1,
                        dtype="int16",
                        samplerate=RATE,
                    )
            except (ValueError, sd.PortAudioError) as exc:
                raise AudioError(
                    "Audio device unavailable. Select your default microphone and speaker in "
                    "OS sound settings and allow microphone access. Run on your local computer, "
                    "not a headless SSH server."
                ) from exc
        if self.save_audio:
            self.wav_file = self.save_audio.open("xb")  # Never overwrite a recording.
            try:
                self.wav = wave.open(self.wav_file, "wb")
                self.wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            except BaseException:
                self.wav_file.close()
                raise
        return self

    def start(self):
        if not self.no_playback:
            self.output_stream = self.sd.RawOutputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAMES,
                device=self.output_device,
                callback=self._speaker,
            )
            self.output_stream.start()
        if not self.input_wav:
            self.input_stream = self.sd.RawInputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAMES,
                device=self.input_device,
                callback=self._microphone,
            )
            self.input_stream.start()

    def _microphone(self, data, frames, timing, status):
        if status:
            self.input_error = (
                "Microphone overflow/status error; audio could not be "
                "captured reliably."
            )
        try:
            self.microphone.put_nowait(bytes(data))
        except queue.Full:
            self.input_error = (
                "Microphone backlog exceeded 2 seconds; check your connection."
            )

    def _speaker(self, output, frames, timing, status):
        size = len(output)
        with self.lock:
            count = min(size, len(self.output))
            output[:count] = self.output[:count]
            output[count:] = bytes(size - count)
            del self.output[:count]

    def play(self, pcm: bytes):
        if len(pcm) % 2:
            raise AudioError("Received an incomplete PCM16 sample.")
        if self.wav:
            self.wav.writeframesraw(pcm)
        if not self.no_playback:
            with self.lock:
                if len(self.output) + len(pcm) > RATE * 2 * 30:
                    raise AudioError(
                        "Speaker backlog exceeded 30 seconds; stopping instead of "
                        "using unbounded memory."
                    )
                self.output.extend(pcm)

    async def frames(self, stop: asyncio.Event) -> AsyncIterator[bytes]:
        """Yield raw PCM, paced by the microphone or file clock. Never send it."""
        if self.input_wav:
            with wave.open(str(self.input_wav), "rb") as source:
                tail = int(self.tail_seconds * RATE / FRAMES)
                while not stop.is_set():
                    pcm = source.readframes(FRAMES)
                    if not pcm:
                        if tail == 0:
                            return
                        tail -= 1
                    yield pcm.ljust(FRAME_BYTES, b"\0")
                    await asyncio.sleep(FRAMES / RATE)
        else:
            while not stop.is_set():
                if self.input_error:
                    raise AudioError(self.input_error)
                try:
                    pcm = self.microphone.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.005)
                    continue
                yield pcm

    def stop_microphone(self):
        if self.input_stream:
            self.input_stream.abort()
            self.input_stream.close()
            self.input_stream = None

    async def drain(self):
        async with asyncio.timeout(35):
            while self.output:  # noqa: ASYNC110 - wait for the callback-owned buffer
                await asyncio.sleep(0.02)
            if self.output_stream:
                # Empty callback buffer does not mean the last hardware frame has played.
                await asyncio.sleep(float(self.output_stream.latency) + FRAMES / RATE)

    def __exit__(self, *_):
        self.stop_microphone()
        if self.output_stream:
            self.output_stream.abort()
            self.output_stream.close()
        if self.wav:
            self.wav.close()
        if self.wav_file:
            self.wav_file.close()
