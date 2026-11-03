# Live Audio Transcription Example

Real-time microphone-to-text transcription using the Foundry Local Python SDK with Nemotron ASR.

## Prerequisites

- Python 3.11 through 3.14
- A microphone (optional — falls back to synthetic audio with `--synth` or if PyAudio is unavailable)

## Setup

```bash
pip install -r requirements.txt
```

> **Note:** `pyaudio` is **optional** — it provides cross-platform microphone capture. Without it, the example falls back to synthetic audio for testing.
>
> Install manually if needed:
> ```bash
> pip install pyaudio
> ```

## Run

```bash
python src/app.py
```

Speak into your microphone. Transcription appears in real-time. Press `Ctrl+C` to stop.

To force synthetic audio (e.g., for CI or when no microphone is available):

```bash
python src/app.py --synth
```

## How it works

1. Initializes Foundry Local SDK v2 and loads the Nemotron ASR model
2. Creates an `AudioSession` with a 16kHz/16-bit/mono format descriptor
3. Captures microphone audio via `pyaudio` (or generates synthetic audio as fallback)
4. Pushes PCM chunks into an `ItemQueue`
5. Streams `SpeechSegmentItem` results and reads the terminal `SpeechResultItem`
6. Closes the session before unloading the model

## API

```python
with AudioSession(model) as session, ItemQueue() as queue, Request() as request:
    request.add_item(
        AudioItem.create_format_descriptor("pcm", sample_rate=16000, channels=1)
    )
    request.add_item(queue, transfer_ownership=False)
    session.set_streaming(True)

    queue.push(BytesItem(pcm_bytes))
    queue.mark_finished()

    with session.process_streaming_request(request) as stream:
        for item in stream:
            if isinstance(item, SpeechSegmentItem):
                print(item.text, end="")
```
