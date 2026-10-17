# Copyright (c) Microsoft. All rights reserved.

"""Local function tool that reads an explicitly delegated mailbox Inbox."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from .graph import (
    GRAPH_BASE_URL,
    acquire_graph_token,
    decode_graph_token_claims,
    diagnose_graph_mailbox_access,
    summarize_graph_response,
)
from .runtime import ToolRuntime

NAME = "read_delegated_mailbox_inbox"
logger = logging.getLogger(__name__)


def build_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "name": NAME,
        "description": (
            "Read the latest messages from the Inbox of a mailbox explicitly "
            "named by the user. Use only for another mailbox that has granted "
            "the current Agent User delegated access. Never use it without an "
            "explicit mailbox email address or user principal name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_principal_name": {
                    "type": "string",
                    "description": (
                        "Exact email address or Microsoft Entra user principal "
                        "name of the delegated mailbox."
                    ),
                },
                "top": {
                    "type": "integer",
                    "description": "Number of newest Inbox messages to return.",
                    "minimum": 1,
                    "maximum": 25,
                },
            },
            "required": ["user_principal_name", "top"],
            "additionalProperties": False,
        },
        "strict": True,
    }


async def execute(arguments: dict[str, Any], runtime: ToolRuntime) -> dict[str, Any]:
    mailbox = str(arguments.get("user_principal_name") or "").strip()
    if not mailbox or "@" not in mailbox or any(ch.isspace() for ch in mailbox):
        raise ValueError("A valid delegated mailbox user principal name is required")
    try:
        message_count = int(arguments.get("top", 5))
    except (TypeError, ValueError) as ex:
        raise ValueError("top must be an integer") from ex
    if not 1 <= message_count <= 25:
        raise ValueError("top must be between 1 and 25")

    graph_token = await acquire_graph_token(
        runtime.auth, runtime.auth_handler_name, runtime.context
    )
    if not graph_token:
        return {
            "mailbox": mailbox,
            "error": {
                "code": "graph_token_unavailable",
                "message": (
                    "Could not acquire a Microsoft Graph agentic-user token. "
                    "Confirm admin consent for Mail.Read.Shared."
                ),
            },
        }

    token_diagnostics = decode_graph_token_claims(graph_token)
    logger.info(
        "Microsoft Graph token diagnostics: %s",
        json.dumps(token_diagnostics, sort_keys=True),
    )
    url = (
        f"{GRAPH_BASE_URL}/users/{quote(mailbox, safe='')}"
        "/mailFolders('Inbox')/messages"
    )
    client_request_id = str(uuid4())
    response = await runtime.http_client.get(
        url,
        params={
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,isRead,"
                "importance,webLink,bodyPreview"
            ),
            "$orderby": "receivedDateTime desc",
            "$top": str(message_count),
        },
        headers={
            "Authorization": f"Bearer {graph_token}",
            "client-request-id": client_request_id,
            "return-client-request-id": "true",
        },
    )
    if response.status_code >= 400:
        graph_failure = summarize_graph_response(
            response, client_request_id=client_request_id
        )
        diagnostics = await diagnose_graph_mailbox_access(
            http_client=runtime.http_client,
            graph_token=graph_token,
            mailbox=mailbox,
            token_diagnostics=token_diagnostics,
        )
        logger.warning(
            "Delegated mailbox read failed for %s: %s; diagnostics=%s",
            mailbox,
            json.dumps(graph_failure, sort_keys=True),
            json.dumps(diagnostics, sort_keys=True),
        )
        return {
            "mailbox": mailbox,
            "error": graph_failure,
            "diagnostics": diagnostics,
        }

    payload = response.json()
    messages = payload.get("value", []) if isinstance(payload, dict) else []
    return {
        "mailbox": mailbox,
        "folder": "Inbox",
        "messages": messages if isinstance(messages, list) else [],
    }
