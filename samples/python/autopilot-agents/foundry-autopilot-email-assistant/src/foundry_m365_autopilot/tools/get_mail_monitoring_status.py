# Copyright (c) Microsoft. All rights reserved.

"""Local function tool that returns current mail-monitoring status."""

from __future__ import annotations

from typing import Any

from .graph import authorize_manager_command
from .mail_monitoring import describe_filter
from .runtime import ToolRuntime

NAME = "get_mail_monitoring_status"


def _manager_summary(manager: dict[str, str]) -> dict[str, str]:
    return {
        "displayName": manager.get("displayName", ""),
        "userPrincipalName": manager.get("userPrincipalName", ""),
        "mail": manager.get("mail", ""),
    }


def build_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": NAME,
        "description": (
            "Return the current forwarded-email monitoring status and filter. "
            "Use only for a direct Teams request from the current Manager."
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
    current_manager = _manager_summary(manager)
    config = await runtime.mail_monitor_store.get(tenant_id, agent_user_id)
    if not config or config.get("enabled") is not True:
        return {
            "status": "disabled",
            "enabled": False,
            "currentManager": current_manager,
            "forwardedEmailRule": "Only email forwarded by the current Manager is processed.",
            "config": config,
        }
    if config.get("managerObjectId") != manager.get("id"):
        return {
            "status": "disabled",
            "enabled": False,
            "currentManager": current_manager,
            "reason": "The Agent User's Manager has changed; configure monitoring again.",
            "config": config,
        }
    return {
        "status": "enabled",
        "enabled": True,
        "currentManager": current_manager,
        "forwardedEmailRule": "Only email forwarded by the current Manager is processed.",
        "filterDescription": describe_filter(config["filter"]),
        "sourceText": config.get("sourceText", ""),
        "updatedAt": config.get("updatedAt", ""),
        "config": config,
    }
