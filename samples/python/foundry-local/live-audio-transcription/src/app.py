# Live Audio Transcription — Foundry Local SDK Example (Python)
#
# Tries PyAudio mic capture first; falls back to synthetic PCM if unavailable.
#
# Usage:
#   pip install -r requirements.txt
#   python src/app.py              # Live microphone
#   python src/app.py --synth      # Synthetic 440Hz sine wave

import math
import signal
import struct
import sys
import threading
import time

from foundry_local_sdk import (
    AudioItem,
    AudioSession,
    BytesItem,
    Configuration,
    FoundryLocalManager,
    ItemQueue,
    Request,
    SpeechResultItem,
    SpeechSegmentItem,
    SpeechSegmentKind,
)

RATE = 16000
CHANNELS = 1
CHUNK = RATE // 10


def main():
    use_synth = "--synth" in sys.argv

    print("===========================================================")
    print("   Foundry Local -- Live Audio Transcription Demo (Python)")
    print("===========================================================")
    print()

    config = Configuration(app_name="foundry_local_samples")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    # English-only:
    model_alias = "nemotron-speech-streaming-en-0.6b"
    # Multi-lingual (supports 30+ languages including auto-detect):
    # model_alias = "nvidia-nemotron-3.5-asr-streaming-multilingual-0.6b"
    model = manager.catalog.get_model(model_alias)
    if model is None:
        manager.close()
        raise RuntimeError(f'Model "{model_alias}" not found in catalog')

    if not model.is_cached:
        model.download(
            lambda progress: print(
                f"\rDownloading model: {progress:.2f}%", end="", flush=True
            )
        )
        print()

    print(f"Loading model {model.id}...", end="")
    model.load()
    print("done.")

    stop_event = threading.Event()
    audio_interface = None
    audio_stream = None
    mic_active = False

    if not use_synth:
        try:
            import pyaudio

            audio_interface = pyaudio.PyAudio()
            audio_stream = audio_interface.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            mic_active = True
        except Exception as error:
            print(f"Could not initialize microphone: {error}")
            print("Falling back to synthetic audio test...\n")
            if audio_stream:
                audio_stream.close()
            if audio_interface:
                audio_interface.terminate()
            audio_interface = None
            audio_stream = None

    def request_stop(*_args):
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)

    def produce_audio(queue):
        try:
            if mic_active:
                print("===========================================================")
                print("  LIVE TRANSCRIPTION ACTIVE")
                print("  Speak into your microphone.")
                print("  Press Ctrl+C to stop.")
                print("===========================================================\n")
                while not stop_event.is_set():
                    pcm_data = audio_stream.read(CHUNK, exception_on_overflow=False)
                    if pcm_data:
                        queue.push(BytesItem(pcm_data))
            else:
                print("Pushing synthetic audio (440Hz sine, 2s)...")
                total_samples = RATE * 2
                pcm_bytes = bytearray(total_samples * 2)
                for index in range(total_samples):
                    timestamp = index / RATE
                    sample = int(32767 * 0.5 * math.sin(2 * math.pi * 440 * timestamp))
                    struct.pack_into("<h", pcm_bytes, index * 2, sample)

                chunk_size = CHUNK * 2
                for offset in range(0, len(pcm_bytes), chunk_size):
                    if stop_event.is_set():
                        break
                    queue.push(BytesItem(pcm_bytes[offset : offset + chunk_size]))
                    time.sleep(0.1)
                print("✓ Synthetic audio pushed")
        finally:
            queue.mark_finished()

    try:
        with (
            AudioSession(model) as session,
            ItemQueue() as audio_queue,
            Request() as request,
        ):
            request.add_item(
                AudioItem.create_format_descriptor(
                    "pcm", sample_rate=RATE, channels=CHANNELS
                ),
                transfer_ownership=True,
            )
            request.add_item(audio_queue, transfer_ownership=False)
            session.set_streaming(True)

            producer = threading.Thread(
                target=produce_audio, args=(audio_queue,), daemon=True
            )
            producer.start()

            print("✓ Session started")
            with session.process_streaming_request(request) as stream:
                for item in stream:
                    if isinstance(item, SpeechSegmentItem):
                        if item.kind == SpeechSegmentKind.FINAL:
                            print(f"\n  [FINAL] {item.text}")
                        elif item.text:
                            print(item.text, end="", flush=True)

                with stream.final_response as final_response:
                    result = next(
                        (
                            item
                            for item in final_response
                            if isinstance(item, SpeechResultItem)
                        ),
                        None,
                    )
                    if result is not None and result.text:
                        print(f"\nTranscript: {result.text}")

            producer.join(timeout=5)
    finally:
        stop_event.set()
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        if audio_interface:
            audio_interface.terminate()
        if model.is_loaded:
            model.unload()
        manager.close()
        print("✓ Done")


if __name__ == "__main__":
    main()
