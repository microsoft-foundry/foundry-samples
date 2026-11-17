"""
DESCRIPTION:
    This sample demonstrates reading a persisted voice conversation back over
    the conversation API exposed by `project_client.voice_agents.conversations`:
    the conversation envelope, its responses (model inference turns), and its
    ordered items (the transcript). Conversations are created and written by
    the voice orchestrator during a live session; this client can only read
    them, and only when effective session storage is enabled (see
    voice_agent_basic.py). Use voice_agent_conversations.py for read-only
    discovery/list/get and separately confirmed, ID-targeted deletion.

    Runs with no setup beyond the endpoint: if FOUNDRY_VOICE_CONVERSATION_ID is
    not set, this sample creates a temporary voice agent, holds one short
    realtime text turn to produce a real conversation, reads it back, then
    deletes the conversation and agent version it created. Set FOUNDRY_VOICE_AGENT_NAME to hold
    that conversation against your own existing agent instead -- it is never
    created, modified, or deleted by this sample. Additionally set
    FOUNDRY_VOICE_CONVERSATION_ID to skip holding a new conversation entirely
    and just read back one your agent already produced.

USAGE:
    python voice_agent_read_conversation.py

    Before running the sample:

    pip install "azure-ai-projects[voice]==2.11.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint.
    2) FOUNDRY_VOICE_AGENT_NAME - Optional. The name of an existing voice agent
       (configured with `store=True`) to hold or read a conversation on.
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
"""

import os
from dotenv import load_dotenv
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
    format_conversation_item,
    hold_sample_conversation,
    require_new_agent,
    safe_print,
    sample_agent_name,
)


def read_conversation(
    conversations: VoiceAgentsConversationsOperations,
    agent_name: str,
    conversation_id: str,
) -> None:
    """Read the envelope, responses and chronologically ordered transcript."""
    conversation = conversations.get(agent_name, conversation_id)
    print(
        f"Conversation {conversation.id}: status={conversation.status}, "
        f"created_at={conversation.created_at}"
    )
    print("Responses:")
    for response in conversations.list_responses(agent_name, conversation_id):
        if not response.id:
            raise RuntimeError("The stored response has no response ID.")
        print(f"  - {response.id}: status={response.status}")
        detail = conversations.get_response(agent_name, conversation_id, response.id)
        print(f"      usage={detail.usage}")
        for response_item in conversations.list_response_items(
            agent_name, conversation_id, response.id
        ):
            print(f"      item {response_item['type']} id={response_item.get('id')}")

    print("Items (transcript):")
    for item in conversations.list_items(agent_name, conversation_id, order="asc"):
        safe_print(f"  - {format_conversation_item(item)}")
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            single = conversations.get_item(agent_name, conversation_id, item_id)
            print(f"      fetched item id={single.get('id')}")


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
    owns_agent = not agent_name
    agent_name = agent_name or sample_agent_name("sample-read-conversation-agent")

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        conversations = project_client.voice_agents.conversations
        created_version = None
        created_conversation_id = None
        try:
            if not conversation_id:
                print(f"Holding a short sample conversation with '{agent_name}'...")
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
            read_conversation(conversations, agent_name, conversation_id)
        except HttpResponseError as error:
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
