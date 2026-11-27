# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Graph helpers shared only by local mail function tools."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote
from uuid import uuid4

import httpx
from microsoft_agents.hosting.core import Authorization, TurnContext

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MANAGER_CACHE_TTL_SECONDS = 3600

logger = logging.getLogger(__name__)


async def acquire_graph_token(
    auth: Authorization,
    auth_handler_name: Optional[str],
    context: TurnContext,
) -> Optional[str]:
    if not auth or not auth_handler_name:
        return None
    try:
        exchanged = await auth.exchange_token(
            context,
            scopes=[GRAPH_SCOPE],
            auth_handler_id=auth_handler_name,
        )
        return getattr(exchanged, "token", None) or getattr(
            exchanged, "access_token", None
        )
    except Exception:
        logger.exception("Failed to acquire Microsoft Graph agentic-user token")
        return None


def decode_graph_token_claims(token: str) -> dict[str, Any]:
    """Return a non-secret subset of JWT claims for runtime diagnostics."""

    diagnostics: dict[str, Any] = {
        "token_format": "jwt" if token.count(".") == 2 else "opaque",
    }
    if diagnostics["token_format"] != "jwt":
        return diagnostics
    try:
        encoded_payload = token.split(".", 2)[1]
        encoded_payload += "=" * (-len(encoded_payload) % 4)
        claims = json.loads(
            base64.urlsafe_b64decode(encoded_payload.encode("ascii")).decode("utf-8")
        )
    except Exception as ex:
        diagnostics["decode_error"] = type(ex).__name__
        return diagnostics

    scopes = str(claims.get("scp") or "").split()
    actor = claims.get("act")
    diagnostics.update(
        {
            "aud": claims.get("aud"),
            "oid": claims.get("oid"),
            "tenant_id": claims.get("tid"),
            "username": claims.get("preferred_username") or claims.get("upn"),
            "scopes": sorted(scopes),
            "has_mail_read_shared": "Mail.Read.Shared" in scopes,
            "identity_type": claims.get("idtyp"),
            "client_app_id": claims.get("azp") or claims.get("appid"),
            "actor": actor if isinstance(actor, dict) else None,
        }
    )
    return {key: value for key, value in diagnostics.items() if value is not None}


def get_agent_user_scope(
    context: TurnContext, graph_token: str = ""
) -> Optional[tuple[str, str]]:
    recipient = getattr(getattr(context, "activity", None), "recipient", None)
    token_claims = decode_graph_token_claims(graph_token) if graph_token else {}
    tenant_id = str(
        getattr(recipient, "tenant_id", "") or token_claims.get("tenant_id", "")
    ).strip()
    agent_user_id = str(
        getattr(recipient, "agentic_user_id", "") or token_claims.get("oid", "")
    ).strip()
    if not tenant_id or not agent_user_id:
        return None
    return tenant_id, agent_user_id


async def get_agent_manager(
    graph_token: str,
    context: TurnContext,
    http_client: httpx.AsyncClient,
    manager_cache: dict[str, tuple[float, dict[str, str]]],
) -> Optional[dict[str, str]]:
    """Resolve and briefly cache the current Agent User's Entra manager."""

    recipient = getattr(getattr(context, "activity", None), "recipient", None)
    token_claims = decode_graph_token_claims(graph_token)
    tenant_id = str(
        getattr(recipient, "tenant_id", "") or token_claims.get("tenant_id", "")
    )
    agent_user_id = str(
        getattr(recipient, "agentic_user_id", "") or token_claims.get("oid", "")
    )
    cache_key = f"{tenant_id}:{agent_user_id}" if agent_user_id else ""
    cached = manager_cache.get(cache_key) if cache_key else None
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    response = await http_client.get(
        f"{GRAPH_BASE_URL}/me",
        params={
            "$select": "id,userPrincipalName,mail",
            "$expand": "manager($select=id,displayName,userPrincipalName,mail)",
        },
        headers={"Authorization": f"Bearer {graph_token}"},
    )
    if response.status_code >= 400:
        logger.error(
            "Failed to resolve Agent User manager from Graph (%s): %s",
            response.status_code,
            response.text,
        )
        return None

    payload = response.json()
    manager = payload.get("manager") if isinstance(payload, dict) else None
    if not isinstance(manager, dict) or not manager.get("id"):
        return None
    normalized = {
        key: str(manager.get(key) or "")
        for key in ("id", "displayName", "userPrincipalName", "mail")
    }
    if cache_key:
        manager_cache[cache_key] = (now + MANAGER_CACHE_TTL_SECONDS, normalized)
    logger.info(
        "Resolved Agent User manager: manager_id=%s, manager_upn=%s",
        normalized["id"],
        normalized["userPrincipalName"],
    )
    return normalized


def get_first_value(value: Any, *names: str) -> Any:
    if value is None:
        return ""
    if isinstance(value, dict):
        for name in names:
            item = value.get(name)
            if item is not None and item != "":
                return item
        return ""
    for name in names:
        item = getattr(value, name, None)
        if item is not None and item != "":
            return item
    return ""


async def authorize_manager_command(runtime: Any) -> tuple[dict[str, str], str, str]:
    activity = getattr(runtime.context, "activity", None)
    channel_id = str(getattr(activity, "channel_id", "") or "").casefold()
    if channel_id != "msteams":
        raise PermissionError(
            "Mail monitoring can only be configured by the Manager in Teams."
        )

    graph_token = await acquire_graph_token(
        runtime.auth, runtime.auth_handler_name, runtime.context
    )
    if not graph_token:
        raise PermissionError("A Microsoft Graph Agent User token is unavailable.")
    manager = await get_agent_manager(
        graph_token, runtime.context, runtime.http_client, runtime.manager_cache
    )
    if not manager:
        raise PermissionError("The current Agent User's Manager cannot be resolved.")

    sender = getattr(activity, "from_property", None)
    sender_object_id = str(
        get_first_value(sender, "aad_object_id", "aadObjectId")
        or get_first_value(sender, "id")
        or ""
    ).strip()
    if sender_object_id.casefold() != manager.get("id", "").casefold():
        raise PermissionError(
            "Only the current Agent User's Manager can change or view mail monitoring."
        )

    scope = get_agent_user_scope(runtime.context, graph_token)
    if not scope:
        raise PermissionError("Tenant ID or Agent User ID is unavailable.")
    return manager, scope[0], scope[1]


def summarize_graph_response(
    response: Any, *, client_request_id: str
) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    graph_error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(graph_error, dict):
        graph_error = {}
    headers = getattr(response, "headers", {}) or {}
    return {
        "code": graph_error.get("code") or f"http_{response.status_code}",
        "message": graph_error.get("message")
        or getattr(response, "text", "")
        or "Graph request failed",
        "http_status": response.status_code,
        "request_id": headers.get("request-id"),
        "client_request_id": headers.get("client-request-id") or client_request_id,
    }


async def diagnose_graph_mailbox_access(
    *,
    http_client: httpx.AsyncClient,
    graph_token: str,
    mailbox: str,
    token_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Probe Graph boundaries after a delegated-mailbox request fails."""

    encoded_mailbox = quote(mailbox, safe="")
    probes = [
        ("current_user", f"{GRAPH_BASE_URL}/me", {"$select": "id,userPrincipalName,mail"}),
        ("current_user_inbox", f"{GRAPH_BASE_URL}/me/mailFolders('Inbox')", {"$select": "id,displayName"}),
        ("target_user", f"{GRAPH_BASE_URL}/users/{encoded_mailbox}", {"$select": "id,userPrincipalName,mail"}),
        ("target_inbox", f"{GRAPH_BASE_URL}/users/{encoded_mailbox}/mailFolders('Inbox')", {"$select": "id,displayName"}),
    ]
    results: list[dict[str, Any]] = []
    target_user_id: Optional[str] = None

    for name, url, params in probes:
        client_request_id = str(uuid4())
        try:
            response = await http_client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {graph_token}",
                    "client-request-id": client_request_id,
                    "return-client-request-id": "true",
                },
            )
            summary = summarize_graph_response(response, client_request_id=client_request_id)
            result: dict[str, Any] = {
                "name": name,
                "http_status": summary["http_status"],
                "code": summary["code"],
                "request_id": summary["request_id"],
                "client_request_id": summary["client_request_id"],
            }
            if response.status_code < 400:
                result["code"] = "ok"
                try:
                    payload = response.json()
                except Exception:
                    payload = {}
                if name == "current_user" and isinstance(payload, dict):
                    result["resolved_id"] = payload.get("id")
                    result["resolved_upn"] = payload.get("userPrincipalName")
                elif name == "target_user" and isinstance(payload, dict):
                    target_user_id = payload.get("id")
                    result["resolved_id"] = target_user_id
                    result["resolved_upn"] = payload.get("userPrincipalName")
                elif isinstance(payload, dict):
                    result["folder_id_present"] = bool(payload.get("id"))
                    result["display_name"] = payload.get("displayName")
            results.append({key: value for key, value in result.items() if value is not None})
        except Exception as ex:
            results.append(
                {"name": name, "code": "probe_exception", "exception_type": type(ex).__name__}
            )

    if target_user_id:
        client_request_id = str(uuid4())
        url = (
            f"{GRAPH_BASE_URL}/users/{quote(str(target_user_id), safe='')}"
            "/mailFolders('Inbox')"
        )
        try:
            response = await http_client.get(
                url,
                params={"$select": "id,displayName"},
                headers={
                    "Authorization": f"Bearer {graph_token}",
                    "client-request-id": client_request_id,
                    "return-client-request-id": "true",
                },
            )
            summary = summarize_graph_response(response, client_request_id=client_request_id)
            results.append(
                {
                    "name": "target_inbox_by_object_id",
                    "http_status": summary["http_status"],
                    "code": "ok" if response.status_code < 400 else summary["code"],
                    "request_id": summary["request_id"],
                    "client_request_id": summary["client_request_id"],
                }
            )
        except Exception as ex:
            results.append(
                {
                    "name": "target_inbox_by_object_id",
                    "code": "probe_exception",
                    "exception_type": type(ex).__name__,
                }
            )
    return {"token": token_diagnostics, "probes": results}
