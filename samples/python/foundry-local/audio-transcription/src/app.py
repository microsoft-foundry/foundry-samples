# <complete_code>
# <imports>
import sys
from pathlib import Path

from foundry_local_sdk import (
    AudioItem,
    AudioSession,
    Configuration,
    FoundryLocalManager,
    Request,
    SpeechResultItem,
    TextItem,
)

# </imports>


def download_if_needed(model) -> None:
    if model.is_cached:
        print(f"Using cached model {model.id}.")
        return
    model.download(
        lambda progress: print(
            f"\rDownloading model: {progress:.2f}%",
            end="",
            flush=True,
        )
    )
    print()


def response_text(response) -> str:
    parts = []
    for item in response:
        if isinstance(item, SpeechResultItem):
            parts.append(item.text)
        elif isinstance(item, TextItem):
            parts.append(item.text)
    return "".join(parts)


# <init>
# Initialize the Foundry Local SDK
config = Configuration(app_name="foundry_local_samples")
FoundryLocalManager.initialize(config)
manager = FoundryLocalManager.instance

# Load the speech-to-text model from the catalog.
model = manager.catalog.get_model("whisper-tiny")
if model is None:
    raise RuntimeError("Model 'whisper-tiny' was not found in the catalog.")

download_if_needed(model)
model.load()
print("Model loaded.")
# </init>

try:
    # <transcription>
    # Create a native audio session and transcribe the file.
    audio_file = Path(sys.argv[1] if len(sys.argv) > 1 else "Recording.mp3")
    with AudioSession(model) as session:
        with Request().add_item(AudioItem.from_uri(str(audio_file))) as request:
            with session.process_request(request) as response:
                print("Transcription:")
                print(response_text(response))
# </transcription>
finally:
    # Clean up
    if model.is_loaded:
        model.unload()
    manager.close()
# </complete_code>
