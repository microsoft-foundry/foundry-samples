# Copyright (c) Microsoft. All rights reserved.

"""Persist and resume authenticated Teams conversations for proactive messages."""

from __future__ import annotations

from typing import Any

from microsoft_agents.activity import Activity, ActivityTypes
from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.hosting.core.app.proactive import Conversation

CONVERSATION_RECORD_VERSION = "1.0"


def build_conversation_record(context: TurnContext) -> dict[str, Any]:
    conversation = Conversation.from_turn_context(context)
    conversation.validate()
    return {
        "version": CONVERSATION_RECORD_VERSION,
        "conversation": conversation.store_item_to_json(),
    }


async def send_proactive_message(
    adapter: Any,
    record: dict[str, Any],
    text: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    if record.get("version") != CONVERSATION_RECORD_VERSION:
        raise ValueError("Unsupported proactive conversation record version")
    conversation_payload = record.get("conversation")
    if not isinstance(conversation_payload, dict):
        raise ValueError("Proactive conversation record is missing conversation data")

    conversation = Conversation.from_json_to_store_item(conversation_payload)
    conversation.validate()
    claims = Conversation.identity_from_claims(conversation.claims)
    continuation = conversation.conversation_reference.get_continuation_activity()

    async def send(turn_context: TurnContext) -> None:
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text=text,
                attachments=attachments or [],
            )
        )

    await adapter.continue_conversation_with_claims(claims, continuation, send)
