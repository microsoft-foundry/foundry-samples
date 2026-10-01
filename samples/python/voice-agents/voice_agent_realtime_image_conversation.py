"""
Send one text-and-image turn to an existing Microsoft Foundry voice agent.

Set FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_AGENT_NAME, and
FOUNDRY_VOICE_AGENT_IMAGE_PATH before running the sample. Optionally set
FOUNDRY_VOICE_AGENT_IMAGE_PROMPT.
"""

import argparse
import base64
import os
from pathlib import Path
from typing import Final

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseAudioTranscriptDone,
    RealtimeServerEventResponseDone,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

MAX_IMAGE_BYTES: Final = 8 * 1024 * 1024
DEFAULT_IMAGE_PROMPT: Final = "Describe this image briefly."
IMAGE_MEDIA_TYPES: Final = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

load_dotenv()


def image_data_url(path: Path) -> str:
    """Read and validate an image, and return a Base64 data URL."""
    validate_image(path, path.stat().st_size)
    image = path.read_bytes()
    media_type = validate_image(path, len(image))
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def validate_image(path: Path, size: int) -> str:
    """Validate a sample image extension and byte count."""
    media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError("Choose a JPEG, PNG, or WebP image.")
    if size == 0:
        raise ValueError("The image must not be empty.")
    if size > MAX_IMAGE_BYTES:
        raise ValueError("Choose an image no larger than 8 MiB.")
    return media_type


# <image_turn>
def send_image_turn(connection, data_url: str, prompt: str) -> None:
    """Send one ordered text-and-image item and request exactly one response."""
    text = prompt.strip() or DEFAULT_IMAGE_PROMPT
    item = RealtimeConversationItemMessageUser(
        type=RealtimeConversationItemType.MESSAGE,
        content=[
            RealtimeConversationItemMessageUserContent(type="input_text", text=text),
            RealtimeConversationItemMessageUserContent(
                type="input_image",
                image_url=data_url,
                detail="low",
            ),
        ],
    )
    connection.conversation.item.create(item=item)
    connection.response.create()
# </image_turn>


def receive_response(connection) -> None:
    """Print the final text transcript and require a completed response."""
    while True:
        event = connection.recv(timeout=45)
        if isinstance(event, RealtimeServerEventResponseAudioTranscriptDone):
            print(f"Agent: {event.transcript}")
        elif isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        elif isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status != "completed":
                raise RuntimeError(f"Response status: {event.response.status}")
            return


def self_test() -> None:
    """Validate image rules, content ordering, and response-request count."""

    class ItemOperations:
        def __init__(self) -> None:
            self.items = []

        def create(self, *, item) -> None:
            self.items.append(item)

    class ResponseOperations:
        def __init__(self) -> None:
            self.count = 0

        def create(self) -> None:
            self.count += 1

    class FakeConnection:
        def __init__(self) -> None:
            self.conversation = type("Conversation", (), {"item": ItemOperations()})()
            self.response = ResponseOperations()

    connection = FakeConnection()
    send_image_turn(connection, "data:image/png;base64,iVBORw==", "  ")
    item = connection.conversation.item.items[0]
    assert [part.type for part in item.content] == ["input_text", "input_image"]
    assert item.content[0].text == DEFAULT_IMAGE_PROMPT
    assert item.content[1].image_url.startswith("data:image/png;base64,")
    assert item.content[1].detail == "low"
    assert len(connection.conversation.item.items) == 1
    assert connection.response.count == 1

    try:
        validate_image(Path("unsupported.gif"), 1)
    except ValueError as error:
        assert "JPEG, PNG, or WebP" in str(error)
    else:
        raise AssertionError("An unsupported extension must fail.")

    assert validate_image(Path("boundary.png"), MAX_IMAGE_BYTES) == "image/png"
    try:
        validate_image(Path("oversize.png"), MAX_IMAGE_BYTES + 1)
    except ValueError as error:
        assert "8 MiB" in str(error)
    else:
        raise AssertionError("An oversized image must fail.")

    print("Image payload validation passed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    image_path = Path(os.environ["FOUNDRY_VOICE_AGENT_IMAGE_PATH"])
    prompt = os.environ.get("FOUNDRY_VOICE_AGENT_IMAGE_PROMPT", DEFAULT_IMAGE_PROMPT)
    data_url = image_data_url(image_path)

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            allow_preview=True,
        ) as project_client,
        project_client.beta.voice_agents.realtime.connect(
            agent_name=agent_name
        ) as connection,
    ):
        send_image_turn(connection, data_url, prompt)
        receive_response(connection)


if __name__ == "__main__":
    main()
