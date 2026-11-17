"""
DESCRIPTION:
    This sample demonstrates reading the persisted audio of a voice
    conversation via `project_client.voice_agents.conversations`, both the
    merged whole-call recording and a single turn's audio segment. For each it
    reads the metadata first, then streams the WAV bytes to a local file. The
    merged recording is stereo: the caller on the left channel and the agent
    on the right.

    Audio is available only after the session has ended and only when the
    agent was configured with `store=True`. For bring-your-own-storage (BYOS)
    accounts the metadata carries a `blob_uri`; BlobClient downloads it using
    the caller's DefaultAzureCredential, which needs Storage Blob Data Reader.
    No SAS token or project-managed-storage fallback is used.

    Runs with no setup beyond the endpoint: if FOUNDRY_VOICE_CONVERSATION_ID is
    not set, this sample creates a temporary voice agent, holds one short
    realtime text turn to produce a real conversation, then reads its audio
    back -- the agent's reply is real synthesized speech either way, so both
    the merged recording and the reply's own audio segment are available even
    though the turn itself was typed. Set FOUNDRY_VOICE_AGENT_NAME to hold that
    conversation against your own existing agent instead -- it is never
    created, modified, or deleted by this sample. Additionally set
    FOUNDRY_VOICE_CONVERSATION_ID to skip holding a new conversation entirely
    and just read back the audio of one your agent already produced.

USAGE:
    python voice_agent_read_conversation_audio.py

    Before running the sample:

    pip install "azure-ai-projects[voice]==2.11.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint.
    2) FOUNDRY_VOICE_AGENT_NAME - Optional. The name of an existing voice
       agent (configured with `store=True`) to hold or read a conversation on.
       Defaults to a temporary agent, created and deleted by this sample, when
       unset.
    3) FOUNDRY_VOICE_CONVERSATION_ID - Optional. The id of a persisted
       conversation owned by FOUNDRY_VOICE_AGENT_NAME. If unset, this sample
       holds one short realtime text turn to produce one; see
       voice_agent_util.py in this folder and
       voice_agent_realtime_text_conversation.py for a full interactive
       version.
    4) FOUNDRY_VOICE_AGENT_MODEL - Optional. The realtime model deployment name,
       used only when creating the temporary agent. Defaults to "gpt-realtime".
    5) FOUNDRY_VOICE_AUDIO_OUTPUT_DIR - Optional existing output directory.
       Defaults to the current directory. Existing files are never overwritten.
"""

import os
from collections.abc import Iterable
from pathlib import Path

from dotenv import load_dotenv
from azure.core.credentials import TokenCredential
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    VoiceAgentAudioConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentDefinition,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)
from azure.ai.projects.operations import VoiceAgentsConversationsOperations

from voice_agent_util import (
    hold_sample_conversation,
    require_new_agent,
    sample_agent_name,
)
from voice_agent_storage_util import (
    audio_output_path,
    save_recording,
    write_audio_file,
)


def stream_to_wav(chunks: Iterable[bytes], output_path: str | Path) -> None:
    """Write a streamed audio-content response to a local WAV file.

    :param chunks: An iterable of audio byte chunks.
    :param output_path: The local output path.
    :type chunks: collections.abc.Iterable[bytes]
    :type output_path: str
    """
    saved = write_audio_file(chunks, output_path)
    print(f"Wrote {saved}")


def read_merged_recording(
    conversations: VoiceAgentsConversationsOperations,
    agent_name: str,
    conversation_id: str,
    *,
    credential: TokenCredential | None = None,
    output_dir: str | Path = ".",
) -> Path:
    """Read the merged whole-call stereo recording (left=user, right=agent).

    :param conversations: The conversation operations client.
    :param agent_name: The voice agent name.
    :param conversation_id: The persisted conversation id.
    :type conversations: azure.ai.projects.operations.VoiceAgentsConversationsOperations
    :type agent_name: str
    :type conversation_id: str
    """
    try:
        recording = conversations.get_audio(agent_name, conversation_id)
    except HttpResponseError as e:
        # A 404 means no merged recording exists for this conversation, for example because the
        # agent was configured with `store=False`, or the session has not finished finalizing yet.
        if e.status_code == 404:
            raise RuntimeError(
                "No merged recording is available. Use a completed conversation with store=True."
            ) from e
        raise

    print(
        f"Recording: format={recording.format}, sample_rate={recording.sample_rate}, "
        f"channels={recording.channels}, duration_ms={recording.duration_ms}"
    )

    saved = save_recording(
        audio_output_path(output_dir, conversation_id),
        credential=credential,
        blob_uri=recording.blob_uri,
        download=lambda: conversations.download_audio(agent_name, conversation_id),
    )
    print(f"Wrote {saved}")
    return saved


def read_first_item_audio(
    conversations: VoiceAgentsConversationsOperations,
    agent_name: str,
    conversation_id: str,
    *,
    credential: TokenCredential | None = None,
    output_dir: str | Path = ".",
) -> Path:
    """Read the audio segment of the first conversation item that has one.

    :param conversations: The conversation operations client.
    :param agent_name: The voice agent name.
    :param conversation_id: The persisted conversation id.
    :type conversations: azure.ai.projects.operations.VoiceAgentsConversationsOperations
    :type agent_name: str
    :type conversation_id: str
    """
    for item in conversations.list_items(agent_name, conversation_id, order="asc"):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        try:
            metadata = conversations.get_audio_item(
                agent_name, conversation_id, item_id
            )
        except HttpResponseError as e:
            # A 404 means this item has no persisted audio (for example, a text-only turn).
            if e.status_code == 404:
                continue
            raise

        print(
            f"Item {item_id}: role={metadata.role}, duration_ms={metadata.duration_ms}"
        )
        saved = save_recording(
            audio_output_path(output_dir, conversation_id, item_id),
            credential=credential,
            blob_uri=metadata.blob_uri,
            download=lambda: conversations.download_audio_item(
                agent_name, conversation_id, item_id
            ),
        )
        print(f"Wrote {saved}")
        return saved

    raise RuntimeError("No conversation item with persisted audio was found.")


def main() -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ.get("FOUNDRY_VOICE_AGENT_NAME") or None
    conversation_id = os.environ.get("FOUNDRY_VOICE_CONVERSATION_ID") or None
    if conversation_id and not agent_name:
        raise ValueError(
            "FOUNDRY_VOICE_AGENT_NAME is required with FOUNDRY_VOICE_CONVERSATION_ID."
        )
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    output_dir = Path(os.environ.get("FOUNDRY_VOICE_AUDIO_OUTPUT_DIR") or ".")
    if not output_dir.is_dir():
        raise ValueError(
            "FOUNDRY_VOICE_AUDIO_OUTPUT_DIR must be an existing directory."
        )
    # Only create (and later clean up) a temporary agent when the caller didn't name their own --
    # creating a version on someone's existing agent could unexpectedly mutate it, and deleting
    # that version afterward could delete the agent entirely if it was its only version.
    owns_agent = not agent_name
    agent_name = agent_name or sample_agent_name("sample-read-conversation-audio-agent")

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        conversations = project_client.voice_agents.conversations
        created_version = None
        created_conversation_id = None
        written_paths: list[Path] = []
        try:
            if not conversation_id:
                print(
                    f"No FOUNDRY_VOICE_CONVERSATION_ID set; holding a short conversation with "
                    f"'{agent_name}' first..."
                )
                if owns_agent:
                    require_new_agent(project_client, agent_name)
                    created_version = project_client.agents.create_version(
                        agent_name=agent_name,
                        definition=VoiceAgentDefinition(
                            model_type=VoiceModelType.MANAGED,
                            model=model,
                            instructions="You are a friendly voice assistant. Keep replies short and natural.",
                            audio=VoiceAgentAudioConfig(
                                output=VoiceAgentAudioOutputConfig(
                                    voice="en-US-AvaNeural",
                                    voice_type=VoiceType.AZURE_STANDARD,
                                ),
                            ),
                            output_modalities=[VoiceOutputModality.AUDIO],
                            store=True,
                        ),
                    )
                conversation_id = hold_sample_conversation(project_client, agent_name)
                created_conversation_id = conversation_id
                print(f"Created conversation: {conversation_id}")

            written_paths.append(
                read_merged_recording(
                    conversations,
                    agent_name,
                    conversation_id,
                    credential=credential,
                    output_dir=output_dir,
                )
            )
            written_paths.append(
                read_first_item_audio(
                    conversations,
                    agent_name,
                    conversation_id,
                    credential=credential,
                    output_dir=output_dir,
                )
            )
        except BaseException as error:
            for path in written_paths:
                path.unlink(missing_ok=True)
            if isinstance(error, HttpResponseError):
                print(
                    f"Service responded with an error: {error.status_code} {error.reason}"
                )
            raise
        finally:
            try:
                if created_conversation_id is not None:
                    conversations.delete(agent_name, created_conversation_id)
                    print(f"Deleted sample conversation: {created_conversation_id}")
            finally:
                if created_version is not None:
                    project_client.agents.delete_version(
                        agent_name=agent_name, agent_version=created_version.version
                    )
                    print(
                        f"Deleted temporary voice agent version: {created_version.version}"
                    )


if __name__ == "__main__":
    main()
