import asyncio
import wave

import pytest

from audio_common import FRAME_BYTES, RATE, Audio, AudioError


def make_wav(path, *, rate=RATE, channels=1):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(bytes(FRAME_BYTES))


def test_audio_accepts_expected_wav_without_loading_sounddevice(tmp_path):
    path = tmp_path / "input.wav"
    make_wav(path)
    with Audio(input_wav=path, no_playback=True, tail_seconds=0):
        pass


def test_audio_rejects_wrong_wav_format(tmp_path):
    path = tmp_path / "input.wav"
    make_wav(path, rate=16000)
    with pytest.raises(AudioError):
        with Audio(input_wav=path, no_playback=True):
            pass


@pytest.mark.asyncio
async def test_wav_frames_are_paced_and_padded(tmp_path):
    path = tmp_path / "input.wav"
    make_wav(path)
    stop = asyncio.Event()
    with Audio(input_wav=path, no_playback=True, tail_seconds=0) as audio:
        frames = [frame async for frame in audio.frames(stop)]
    assert frames == [bytes(FRAME_BYTES)]
