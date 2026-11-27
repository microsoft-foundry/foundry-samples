"""Microsoft Graph helpers for Manager-scoped Meeting Assistant actions."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote

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


async def resolve_online_meeting_by_join_url(
    graph_token: str,
    join_web_url: str,
    http_client: httpx.AsyncClient,
) -> Optional[dict[str, str]]:
    join_web_url = join_web_url.strip()
    if not graph_token or not join_web_url:
        return None
    escaped_join_url = join_web_url.replace("'", "''")
    try:
        response = await http_client.get(
            f"{GRAPH_BASE_URL}/me/onlineMeetings",
            params={
                "$filter": f"JoinWebUrl eq '{escaped_join_url}'",
                "$select": "id,joinWebUrl,chatInfo",
            },
            headers={"Authorization": f"Bearer {graph_token}"},
        )
    except Exception:
        logger.exception("Online meeting lookup failed")
        return None
    if response.status_code >= 400:
        logger.warning(
            "Online meeting lookup unavailable: status=%s", response.status_code
        )
        return None
    payload = response.json()
    values = payload.get("value") if isinstance(payload, dict) else None
    matches = [
        value
        for value in values or []
        if isinstance(value, dict)
        and str(value.get("joinWebUrl") or "").strip() == join_web_url
    ]
    if len(matches) != 1:
        logger.info("Online meeting lookup completed: exactMatch=%s", False)
        return None
    match = matches[0]
    chat_info = match.get("chatInfo")
    result = {
        "onlineMeetingId": str(match.get("id") or "").strip(),
        "threadId": str(
            chat_info.get("threadId") if isinstance(chat_info, dict) else ""
        ).strip(),
        "joinWebUrl": join_web_url,
    }
    logger.info(
        "Online meeting lookup completed: exactMatch=%s thread=%s",
        bool(result["onlineMeetingId"]),
        bool(result["threadId"]),
    )
    return result if result["onlineMeetingId"] else None


async def get_calendar_event_details(
    graph_token: str,
    event_id: str,
    http_client: httpx.AsyncClient,
) -> Optional[dict[str, str]]:
    event_id = event_id.strip()
    if not graph_token or not event_id:
        return None
    try:
        response = await http_client.get(
            f"{GRAPH_BASE_URL}/me/events/{quote(event_id, safe='')}",
            params={"$select": "location,onlineMeeting,onlineMeetingUrl,webLink"},
            headers={"Authorization": f"Bearer {graph_token}"},
        )
    except Exception:
        logger.exception("Calendar event detail lookup failed")
        return None
    if response.status_code >= 400:
        logger.warning(
            "Calendar event detail lookup unavailable: status=%s",
            response.status_code,
        )
        return None

    payload = response.json()
    if not isinstance(payload, dict):
        return None
    location = payload.get("location")
    online_meeting = payload.get("onlineMeeting")
    return {
        "location": str(
            location.get("displayName") if isinstance(location, dict) else ""
        ).strip(),
        "joinWebUrl": str(
            (
                online_meeting.get("joinUrl")
                if isinstance(online_meeting, dict)
                else ""
            )
            or payload.get("onlineMeetingUrl")
            or ""
        ).strip(),
        "webLink": str(payload.get("webLink") or "").strip(),
    }


def decode_graph_token_claims(token: str) -> dict[str, Any]:
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
    diagnostics.update(
        {
            "oid": claims.get("oid"),
            "tenant_id": claims.get("tid"),
            "username": claims.get("preferred_username") or claims.get("upn"),
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


async def authorize_manager_turn(
    *,
    auth: Authorization,
    auth_handler_name: Optional[str],
    context: TurnContext,
    http_client: httpx.AsyncClient,
    manager_cache: dict[str, tuple[float, dict[str, str]]],
) -> tuple[dict[str, str], str, str]:
    activity = getattr(context, "activity", None)
    channel_id = str(getattr(activity, "channel_id", "") or "").casefold()
    if channel_id != "msteams":
        raise PermissionError(
            "Meeting delegation can only be configured by the Manager in Teams."
        )

    graph_token = await acquire_graph_token(auth, auth_handler_name, context)
    if not graph_token:
        raise PermissionError("A Microsoft Graph Agent User token is unavailable.")
    manager = await get_agent_manager(graph_token, context, http_client, manager_cache)
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
            "Only this Digital Worker's current Manager can configure meeting delegation."
        )

    scope = get_agent_user_scope(context, graph_token)
    if not scope:
        raise PermissionError("Tenant ID or Agent User ID is unavailable.")
    return manager, scope[0], scope[1]
