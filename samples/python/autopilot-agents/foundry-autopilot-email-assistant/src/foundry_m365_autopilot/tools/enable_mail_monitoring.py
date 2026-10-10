# Copyright (c) Microsoft. All rights reserved.

"""Local function tool that resumes an existing mail-monitoring rule."""

from __future__ import annotations

import logging
from typing import Any

from .graph import authorize_manager_command
from .mail_monitoring import describe_filter
from .runtime import ToolRuntime

NAME = "enable_mail_monitoring"
logger = logging.getLogger(__name__)


def build_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": NAME,
        "description": (
            "Enable a previously configured forwarded-email monitoring rule "
            "without replacing it. Use only for a direct Teams request from "
            "the current Manager."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    }


async def execute(arguments: dict[str, Any], runtime: ToolRuntime) -> dict[str, Any]:
    manager, tenant_id, agent_user_id = await authorize_manager_command(runtime)
    config = await runtime.mail_monitor_store.get(tenant_id, agent_user_id)
    if not config or not config.get("filter"):
        return {
            "status": "configuration_required",
            "enabled": False,
            "message": "No saved monitoring rule is available. Provide a rule to enable monitoring.",
        }
    if config.get("managerObjectId") != manager.get("id"):
        return {
            "status": "configuration_required",
            "enabled": False,
            "message": (
                "The Agent User's Manager has changed. Provide a new rule to "
                "enable monitoring."
            ),
        }

    config = await runtime.mail_monitor_store.enable(tenant_id, agent_user_id)
    logger.info(
        "Mail monitoring enabled from saved configuration: agent_user_id=%s, manager_id=%s",
        agent_user_id,
        manager.get("id", "(unknown)"),
    )
    return {
        "status": "enabled",
        "enabled": True,
        "filterDescription": describe_filter(config["filter"]),
        "sourceText": config.get("sourceText", ""),
        "storageNotice": "The existing configuration was enabled without changing its rule.",
    }