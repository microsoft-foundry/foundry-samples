# <complete_code>
# <imports>
import sys

from foundry_local_sdk import (
    AudioItem,
    AudioSession,
    ChatSession,
    Configuration,
    FoundryLocalManager,
    MessageItem,
    Request,
    RequestOptions,
    SearchOptions,
    SpeechResultItem,
    TextItem,
)

# </imports>


def download_if_needed(model, label):
    if model.is_cached:
        print(f"Using cached {label} model {model.id}.")
        return
    model.download(
        lambda progress: print(
            f"\rDownloading {label} model: {progress:.2f}%",
            end="",
            flush=True,
        )
    )
    print()


def get_text(response):
    parts = []
    for item in response:
        if isinstance(item, SpeechResultItem):
            parts.append(item.text)
        elif isinstance(item, TextItem):
            parts.append(item.text)
        elif isinstance(item, MessageItem):
            parts.extend(part.text for part in item.parts if isinstance(part, TextItem))
    return "".join(parts)


def main():
    # <init>
    # Initialize the Foundry Local SDK
    config = Configuration(app_name="foundry_local_samples")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance
    # </init>

    audio_path = sys.argv[1] if len(sys.argv) > 1 else "meeting-notes.wav"

    # <transcription>
    # Load the speech-to-text model.
    speech_model = manager.catalog.get_model("whisper-tiny")
    if speech_model is None:
        raise RuntimeError("Model 'whisper-tiny' was not found in the catalog.")
    download_if_needed(speech_model, "speech")
    speech_model.load()
    print("Speech model loaded.")

    try:
        # Transcribe the audio file with a native audio session.
        with AudioSession(speech_model) as session:
            with Request().add_item(AudioItem.from_uri(audio_path)) as request:
                with session.process_request(request) as response:
                    transcription = get_text(response)
        print(f"\nTranscription:\n{transcription}")
    finally:
        # Unload the speech model to free memory.
        if speech_model.is_loaded:
            speech_model.unload()
    # </transcription>

    # <summarization>
    # Load the chat model for summarization.
    chat_model = manager.catalog.get_model("qwen2.5-0.5b")
    if chat_model is None:
        manager.close()
        raise RuntimeError("Model 'qwen2.5-0.5b' was not found in the catalog.")
    download_if_needed(chat_model, "chat")
    chat_model.load()
    print("Chat model loaded.")

    try:
        # Summarize the transcription into organized notes.
        with ChatSession(chat_model) as session:
            session.set_options(
                RequestOptions(
                    search=SearchOptions(temperature=0.2, max_output_tokens=512)
                )
            )
            with (
                Request()
                .add_item(
                    MessageItem.system(
                        "You are a note-taking assistant. Summarize the following "
                        "transcription into organized, concise notes with bullet points."
                    )
                )
                .add_item(MessageItem.user(transcription)) as request
            ):
                with session.process_request(request) as response:
                    summary = get_text(response)
        print(f"\nSummary:\n{summary}")
    finally:
        # Clean up.
        if chat_model.is_loaded:
            chat_model.unload()
        manager.close()
        print("\nDone. Models unloaded.")
    # </summarization>


if __name__ == "__main__":
    main()
# </complete_code>
