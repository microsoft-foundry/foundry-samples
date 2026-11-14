"""Read a Native Live transcript, merged WAV, and first speech-item WAV, read-only.

Run: python voice_agent_live_readback.py
Requires azure-ai-projects[voice]==2.11.0, azure-identity, python-dotenv,
azure-storage-blob>=12.15.0.
Env: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_LIVE_AGENT_NAME (existing Live
agent), FOUNDRY_VOICE_LIVE_CONVERSATION_ID (session.started.conversation_id,
NOT session.id). Optional FOUNDRY_VOICE_LIVE_RECORDING_PATH: a new output WAV.
The first speech-item WAV is saved beside it as <recording-stem>-first-item.wav.
Use voice_agent_live_audio.py --store to produce/read/delete an owned example.
DefaultAzureCredential authenticates. Existing agents/conversations are NEVER
changed or deleted. Requires store=True and captured speech audio. Missing audio
(404) and failed/unavailable recordings are raised, not substituted. BYOS uses
the caller's async Azure credential with Storage Blob Data Reader (or equivalent).
Only validated HTTPS Azure Blob URIs without SAS/query credentials are accepted;
storage failures never fall back to managed downloads. Caller-owned credentials
are not closed here. No storage URI or audio is logged.
Persistence finalization is not a frontend-speech completion signal.
Treat both WAVs as private.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
import os
from pathlib import Path
from uuid import uuid4

from azure.ai.projects import models
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobClient
from dotenv import load_dotenv

from voice_agent_storage_util import validate_blob_uri


async def readback(
    project: AIProjectClient,
    agent_name: str,
    conversation_id: str,
    path: Path,
    *,
    credential: AsyncTokenCredential | None = None,
) -> None:
    """Bound polling, pagination, and download together, not just individual calls."""
    if not conversation_id:
        raise ValueError("A persisted session.started.conversation_id is required.")

    async def read() -> None:
        conversations = project.beta.voice_agents.live_conversations

        def validate_storage(blob_uri: str | None) -> None:
            if blob_uri is not None:
                validate_blob_uri(blob_uri)
                if credential is None:
                    raise ValueError(
                        "BYOS downloads require the caller's async Azure credential."
                    )

        async def save_audio(
            output_path: Path, *, blob_uri: str | None, item_id: str | None = None
        ) -> None:
            raw = output_path.open("xb")
            success = False

            async def write_chunks(chunks: AsyncIterable[bytes | str]) -> None:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise RuntimeError(
                            "The recording download was not binary audio."
                        )
                    raw.write(chunk)

            try:
                with raw:
                    if blob_uri is not None:
                        async with BlobClient.from_blob_url(
                            blob_uri, credential=credential, logging_enable=False
                        ) as blob:
                            download = await blob.download_blob(logging_enable=False)
                            await write_chunks(download.chunks())
                    else:
                        stream = (
                            await conversations.download_audio(
                                agent_name=agent_name, conversation_id=conversation_id
                            )
                            if item_id is None
                            else await conversations.download_audio_item(
                                agent_name=agent_name,
                                conversation_id=conversation_id,
                                item_id=item_id,
                            )
                        )
                        await write_chunks(stream)
                    if raw.tell() == 0:
                        raise RuntimeError("Live returned an empty recording.")
                success = True
            finally:
                if not success:
                    output_path.unlink()

        while True:
            conversation = await conversations.get(
                agent_name=agent_name, conversation_id=conversation_id
            )
            if conversation.status == "completed":
                break
            if conversation.status != "in_progress":
                raise RuntimeError(
                    f"Live persistence failed (status={conversation.status})."
                )
            await asyncio.sleep(1)
        first_speech_id = None
        async for item in conversations.list_items(
            agent_name=agent_name, conversation_id=conversation_id, order="asc"
        ):
            if isinstance(
                item,
                (
                    models.VoiceAgentLiveInputConversationItem,
                    models.VoiceAgentLiveOutputConversationItem,
                ),
            ):
                if first_speech_id is None:
                    first_speech_id = item.id
                if item.transcription:
                    print(f"{item.type}: {item.transcription}")
        if not first_speech_id:
            raise RuntimeError(
                "No stored speech item is available for item-level audio readback."
            )
        speech = await conversations.get_item(
            agent_name=agent_name,
            conversation_id=conversation_id,
            item_id=first_speech_id,
        )
        if (
            not isinstance(
                speech,
                (
                    models.VoiceAgentLiveInputConversationItem,
                    models.VoiceAgentLiveOutputConversationItem,
                ),
            )
            or speech.id != first_speech_id
        ):
            raise RuntimeError(
                "Retrieved item does not match the first stored speech item."
            )
        speech_audio = await conversations.get_audio_item(
            agent_name=agent_name,
            conversation_id=conversation_id,
            item_id=first_speech_id,
        )
        if (
            speech_audio.conversation_id != conversation_id
            or speech_audio.item_id != first_speech_id
        ):
            raise RuntimeError(
                "Speech-audio metadata does not match the requested conversation/item."
            )
        speech_blob_uri = speech_audio.blob_uri
        validate_storage(speech_blob_uri)
        while True:
            try:
                recording = await conversations.get_audio(
                    agent_name=agent_name, conversation_id=conversation_id
                )
                break
            except HttpResponseError as error:
                if (
                    error.status_code != 409
                    or getattr(error.error, "code", None) != "recording_not_ready"
                ):
                    raise
                await asyncio.sleep(1)
        recording_blob_uri = recording.blob_uri
        validate_storage(recording_blob_uri)
        item_path = path.with_name(f"{path.stem}-first-item.wav")
        await save_audio(path, blob_uri=recording_blob_uri)
        await save_audio(item_path, blob_uri=speech_blob_uri, item_id=first_speech_id)
        print(f"Saved merged {recording.channels}-channel recording: {path}")
        print(f"Saved first speech-item recording: {item_path}")

    await asyncio.wait_for(read(), timeout=60)


async def main() -> None:
    load_dotenv()
    path = Path(
        os.environ.get("FOUNDRY_VOICE_LIVE_RECORDING_PATH")
        or f"voice-live-recording-{uuid4().hex[:8]}.wav"
    )
    async with (
        DefaultAzureCredential(process_timeout=60) as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        ) as project,
    ):
        await readback(
            project,
            os.environ["FOUNDRY_VOICE_LIVE_AGENT_NAME"],
            os.environ["FOUNDRY_VOICE_LIVE_CONVERSATION_ID"],
            path,
            credential=credential,
        )


if __name__ == "__main__":
    asyncio.run(main())
