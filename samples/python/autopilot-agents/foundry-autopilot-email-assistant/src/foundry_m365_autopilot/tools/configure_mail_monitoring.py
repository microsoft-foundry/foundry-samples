# Copyright (c) Microsoft. All rights reserved.

"""Local function tool that enables or replaces mail monitoring."""

from __future__ import annotations

import logging
from typing import Any

from .graph import authorize_manager_command
from .mail_monitoring import describe_filter
from .runtime import ToolRuntime

NAME = "configure_mail_monitoring"
logger = logging.getLogger(__name__)

CONDITION_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {
            "type": "string",
            "enum": [
                "originalSender.address",
                "subject",
                "body.text",
                "sentAt",
                "importance",
            ],
        },
        "operator": {
            "type": "string",
            "enum": [
                "equals",
                "in",
                "contains",
                "containsAny",
                "before",
                "after",
                "between",
            ],
        },
        "value": {
            "description": (
                "A string, an array of strings for in/containsAny, or an "
                "object with start and end ISO 8601 values for between."
            )
        },
    },
    "required": ["field", "operator", "value"],
    "additionalProperties": False,
}


def build_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": NAME,
        "description": (
            "Enable or replace forwarded-email monitoring for the current "
            "Agent User. Use only for a direct Teams request from the current "
            "Manager. Compile the user's complete natural-language condition "
            "into the simple filter. Ask for clarification before calling if "
            "the condition is ambiguous."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source_text": {
                    "type": "string",
                    "description": "The Manager's original monitoring request.",
                },
                "filter": {
                    "type": "object",
                    "properties": {
                        "match": {"type": "string", "enum": ["all", "any"]},
                        "conditions": {
                            "type": "array",
                            "items": CONDITION_SCHEMA,
                            "minItems": 1,
                            "maxItems": 20,
                        },
                    },
                    "required": ["match", "conditions"],
                    "additionalProperties": False,
                },
            },
            "required": ["source_text", "filter"],
            "additionalProperties": False,
        },
        "strict": False,
    }


async def execute(arguments: dict[str, Any], runtime: ToolRuntime) -> dict[str, Any]:
    manager, tenant_id, agent_user_id = await authorize_manager_command(runtime)
    source_text = str(arguments.get("source_text") or "").strip()
    if not source_text:
        from .mail_monitoring import MailFilterValidationError

        raise MailFilterValidationError("source_text is required")
    config = await runtime.mail_monitor_store.save(
        tenant_id,
        agent_user_id,
        manager,
        source_text,
        arguments.get("filter"),
    )
    logger.info(
        "Mail monitoring configured: agent_user_id=%s, manager_id=%s, condition_count=%d",
        agent_user_id,
        manager.get("id", "(unknown)"),
        len(config["filter"]["conditions"]),
    )
    return {
        "status": "enabled",
        "enabled": True,
        "filterDescription": describe_filter(config["filter"]),
        "sourceText": config["sourceText"],
        "storageNotice": "The configuration is stored in shared Azure Blob Storage.",
    }
