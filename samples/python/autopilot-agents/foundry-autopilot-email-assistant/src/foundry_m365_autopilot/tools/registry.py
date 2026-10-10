# Copyright (c) Microsoft. All rights reserved.

"""Allowlist, definitions, and dispatch for local function tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from . import (
    configure_mail_monitoring,
    disable_mail_monitoring,
    enable_mail_monitoring,
    get_mail_monitoring_status,
    read_delegated_mailbox_inbox,
)
from .mail_monitoring import MailFilterValidationError, MailMonitoringStorageError
from .runtime import ToolRuntime

ToolExecutor = Callable[[dict[str, Any], ToolRuntime], Awaitable[dict[str, Any]]]
logger = logging.getLogger(__name__)

_TOOL_MODULES = (
    read_delegated_mailbox_inbox,
    configure_mail_monitoring,
    enable_mail_monitoring,
    get_mail_monitoring_status,
    disable_mail_monitoring,
)
_EXECUTORS: dict[str, ToolExecutor] = {
    module.NAME: module.execute for module in _TOOL_MODULES
}
_MAIL_MONITORING_TOOLS = frozenset(
    {
        configure_mail_monitoring.NAME,
        enable_mail_monitoring.NAME,
        get_mail_monitoring_status.NAME,
        disable_mail_monitoring.NAME,
    }
)


def build_definitions() -> list[dict[str, Any]]:
    return [module.build_definition() for module in _TOOL_MODULES]


def is_registered(name: str) -> bool:
    return name in _EXECUTORS


def extract_function_calls(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only allowlisted local function calls with correlation IDs."""

    output = response_json.get("output") if isinstance(response_json, dict) else None
    if not isinstance(output, list):
        return []
    return [
        item
        for item in output
        if isinstance(item, dict)
        and item.get("type") == "function_call"
        and is_registered(str(item.get("name") or ""))
        and item.get("call_id")
    ]


async def dispatch(
    name: str, arguments_json: Any, runtime: ToolRuntime
) -> dict[str, Any]:
    executor = _EXECUTORS.get(name)
    if executor is None:
        return {
            "error": {
                "code": "unsupported_tool",
                "message": f"Unsupported local function tool: {name}",
            }
        }
    try:
        arguments = (
            json.loads(arguments_json or "{}")
            if isinstance(arguments_json, str)
            else arguments_json
        )
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
    except (TypeError, ValueError, json.JSONDecodeError) as ex:
        logger.warning("Invalid local function tool arguments: %s", ex)
        return {"error": {"code": "invalid_arguments", "message": str(ex)}}

    try:
        return await executor(arguments, runtime)
    except PermissionError as ex:
        if name in _MAIL_MONITORING_TOOLS:
            logger.warning("Rejected mail-monitoring command: %s", ex)
            return {"error": {"code": "not_authorized", "message": str(ex)}}
        raise
    except (MailFilterValidationError, MailMonitoringStorageError, OSError) as ex:
        if name in _MAIL_MONITORING_TOOLS:
            logger.warning("Mail-monitoring command failed: %s", ex)
            return {"error": {"code": "configuration_failed", "message": str(ex)}}
        raise
    except ValueError as ex:
        if name in _MAIL_MONITORING_TOOLS:
            logger.warning("Mail-monitoring command failed: %s", ex)
            return {"error": {"code": "configuration_failed", "message": str(ex)}}
        logger.warning("Invalid local function tool arguments: %s", ex)
        return {"error": {"code": "invalid_arguments", "message": str(ex)}}
    except TypeError as ex:
        logger.warning("Invalid local function tool arguments: %s", ex)
        return {"error": {"code": "invalid_arguments", "message": str(ex)}}
