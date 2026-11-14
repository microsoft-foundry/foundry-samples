"""Discover, list and get persisted Realtime or Native Live conversations.

Requires azure-ai-projects==2.11.0, python-dotenv and FOUNDRY_PROJECT_ENDPOINT.
Without an agent name, discover voice agents for the selected protocol. With
--agent-name (or FOUNDRY_VOICE_AGENT_NAME), list that agent's conversations.
Add --conversation-id (or FOUNDRY_VOICE_CONVERSATION_ID) to get one envelope.
Listing is bounded by --limit; --before and --order select its cursor and order.

Read-only examples:
    python voice_agent_conversations.py --protocol realtime
    python voice_agent_conversations.py --protocol live --agent-name my-live-agent
    python voice_agent_conversations.py --agent-name my-agent --conversation-id ID

Intentional deletion requires an exact ID twice and --delete:
    python voice_agent_conversations.py --agent-name my-agent --conversation-id ID --delete --confirm-conversation-id ID

Delete cascades to stored items, responses and audio, but does not close an
active session. This sample refuses active conversations and verifies 404 after
deletion. It never creates or modifies an agent and never deletes by list/prefix.
"""

import argparse
import os
import time
from itertools import islice

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    VoiceAgentDefinition,
    VoiceAgentLiveConversation,
    VoiceAgentLiveDefinition,
    VoiceConversation,
    VoiceConversationStatus,
)
from azure.ai.projects.operations import (
    BetaVoiceAgentsLiveConversationsOperations,
    VoiceAgentsConversationsOperations,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

ConversationOperations = (
    VoiceAgentsConversationsOperations | BetaVoiceAgentsLiveConversationsOperations
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=("realtime", "live"), default="realtime")
    parser.add_argument(
        "--agent-name", default=os.environ.get("FOUNDRY_VOICE_AGENT_NAME") or None
    )
    parser.add_argument(
        "--conversation-id",
        default=os.environ.get("FOUNDRY_VOICE_CONVERSATION_ID") or None,
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--order", choices=("asc", "desc"), default="desc")
    parser.add_argument("--before", help="Exact conversation/agent pagination cursor.")
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--confirm-conversation-id")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100.")
    if args.conversation_id and not args.agent_name:
        parser.error("--agent-name is required with --conversation-id.")
    if args.delete and (
        not args.agent_name
        or not args.conversation_id
        or args.confirm_conversation_id != args.conversation_id
    ):
        parser.error(
            "Deletion requires --agent-name, --conversation-id and "
            "--confirm-conversation-id with the same exact ID."
        )
    if args.confirm_conversation_id and not args.delete:
        parser.error("--confirm-conversation-id requires --delete.")
    for identifier in (args.agent_name, args.conversation_id, args.before):
        if identifier is not None and (
            not identifier.strip()
            or any(character in identifier for character in "*/\\?#")
            or identifier in (".", "..")
        ):
            parser.error(
                "Use an exact nonempty agent name or ID, not a path or pattern."
            )
    return args


def conversation_operations(
    client: AIProjectClient, protocol: str
) -> ConversationOperations:
    if protocol == "live":
        return client.beta.voice_agents.live_conversations
    if protocol == "realtime":
        return client.voice_agents.conversations
    raise ValueError("Protocol must be 'realtime' or 'live'.")


def print_conversation(
    conversation: VoiceConversation | VoiceAgentLiveConversation,
) -> None:
    status = conversation.status
    if isinstance(status, VoiceConversationStatus):
        status = status.value
    print(
        f"Conversation {conversation.id}: status={status}, "
        f"created_at={conversation.created_at}, completed_at={conversation.completed_at}"
    )


def delete_conversation(
    conversations: ConversationOperations, agent_name: str, conversation_id: str
) -> None:
    """Delete one explicitly selected, finished conversation, then verify absence."""
    conversation = conversations.get(agent_name, conversation_id)
    if conversation.status not in ("completed", "failed"):
        raise ValueError("Close the session and wait for finalization before deleting.")
    conversations.delete(agent_name, conversation_id)
    for attempt in range(5):
        try:
            conversations.get(agent_name, conversation_id)
        except ResourceNotFoundError:
            print(f"Deleted conversation {conversation_id}; verified HTTP 404.")
            return
        if attempt < 4:
            time.sleep(0.5)
    raise RuntimeError("Deletion returned, but the conversation is still readable.")


def run(client: AIProjectClient, args: argparse.Namespace) -> None:
    expected_type = (
        VoiceAgentLiveDefinition if args.protocol == "live" else VoiceAgentDefinition
    )
    if not args.agent_name:
        print(f"Voice agents using {args.protocol} (at most {args.limit} entries):")
        agents = client.agents.list(
            kind="voice", limit=args.limit, order=args.order, before=args.before
        )
        for agent in islice(agents, args.limit):
            if isinstance(agent.versions.latest.definition, expected_type):
                print(f"  - {agent.name}")
        return

    definition = client.agents.get(
        agent_name=args.agent_name
    ).versions.latest.definition
    if not isinstance(definition, expected_type):
        raise ValueError(
            f"The selected agent does not use {args.protocol}; choose the matching protocol."
        )
    conversations = conversation_operations(client, args.protocol)
    if args.delete:
        delete_conversation(conversations, args.agent_name, args.conversation_id)
    elif args.conversation_id:
        print_conversation(conversations.get(args.agent_name, args.conversation_id))
    else:
        print(f"Conversations for {args.agent_name} (at most {args.limit} entries):")
        for conversation in islice(
            conversations.list(
                args.agent_name,
                limit=args.limit,
                order=args.order,
                before=args.before,
            ),
            args.limit,
        ):
            print_conversation(conversation)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = parse_args(argv)
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as client,
    ):
        run(client, args)


if __name__ == "__main__":
    main()
