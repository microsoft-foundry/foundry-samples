# Copyright (c) Microsoft. All rights reserved.

"""Local function tool that disables current mail monitoring."""

from __future__ import annotations

import logging
from typing import Any

from .graph import authorize_manager_command
from .runtime import ToolRuntime

NAME = "disable_mail_monitoring"
logger = logging.getLogger(__name__)


def build_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": NAME,
        "description": (
            "Disable forwarded-email monitoring for the current Agent User. "
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
    await runtime.mail_monitor_store.disable(tenant_id, agent_user_id)
    logger.info(
        "Mail monitoring disabled: agent_user_id=%s, manager_id=%s",
        agent_user_id,
        manager.get("id", "(unknown)"),
    )
    return {
        "status": "disabled",
        "enabled": False,
        "forwardingRuleNotice": (
            "The Exchange forwarding rule was not changed and must be "
            "disabled separately if no longer needed."
        ),
    }
