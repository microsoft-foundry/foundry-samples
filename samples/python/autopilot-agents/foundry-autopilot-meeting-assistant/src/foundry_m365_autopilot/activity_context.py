"""Safe Activity Protocol context formatting helpers."""

from __future__ import annotations

from typing import Any


def get_activity_value(value: Any, *names: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for name in names:
            item = value.get(name)
            if item is not None and item != "":
                return str(item)
        return ""
    for name in names:
        item = getattr(value, name, None)
        if item is not None and item != "":
            return str(item)
    return ""


def summarize_identifier(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return "(none)"
    if len(value) <= 18:
        return value
    return f"{value[:10]}...{value[-6:]}"


def format_activity_context(activity: Any, session_id: str = "") -> str:
    context = build_activity_context(activity, session_id)
    return "\n".join(
        [
            "Activity context",
            "",
            "User",
            f"- Display name: {context['user']['displayName']}",
            f"- User id: {context['user']['userId']}",
            f"- AAD object id: {context['user']['aadObjectId']}",
            "",
            "Conversation",
            f"- Session id: {context['conversation']['sessionId']}",
            f"- Channel: {context['conversation']['channel']}",
            f"- Conversation id: {context['conversation']['conversationId']}",
            f"- Conversation type: {context['conversation']['conversationType']}",
            f"- Locale: {context['conversation']['locale']}",
            f"- Service URL: {context['conversation']['serviceUrl']}",
            f"- Channel data: {context['conversation']['channelData']}",
            "",
            "Digital Worker",
            f"- Tenant id: {context['digitalWorker']['tenantId']}",
            f"- Agent app id: {context['digitalWorker']['agentAppId']}",
            f"- Agent user id: {context['digitalWorker']['agentUserId']}",
        ]
    )


def build_activity_context(
    activity: Any, session_id: str = ""
) -> dict[str, dict[str, str]]:
    from_property = getattr(activity, "from_property", None)
    recipient = getattr(activity, "recipient", None)
    conversation = getattr(activity, "conversation", None)
    channel_data = getattr(activity, "channel_data", None)
    channel_data_summary = "present" if channel_data else "(none)"

    return {
        "user": {
            "displayName": get_activity_value(from_property, "name") or "(unknown)",
            "userId": summarize_identifier(get_activity_value(from_property, "id")),
            "aadObjectId": summarize_identifier(
                get_activity_value(from_property, "aad_object_id", "aadObjectId")
            ),
        },
        "conversation": {
            "sessionId": session_id or "(not set)",
            "channel": get_activity_value(activity, "channel_id", "channelId")
            or "(unknown)",
            "conversationId": summarize_identifier(
                get_activity_value(conversation, "id")
            ),
            "conversationType": get_activity_value(
                conversation, "conversation_type", "conversationType", "type"
            )
            or "(unknown)",
            "locale": get_activity_value(activity, "locale") or "(unknown)",
            "serviceUrl": "present"
            if get_activity_value(activity, "service_url", "serviceUrl")
            else "(none)",
            "channelData": channel_data_summary,
        },
        "digitalWorker": {
            "tenantId": summarize_identifier(
                get_activity_value(recipient, "tenant_id", "tenantId")
            ),
            "agentAppId": summarize_identifier(
                get_activity_value(recipient, "agentic_app_id", "agenticAppId")
            ),
            "agentUserId": summarize_identifier(
                get_activity_value(recipient, "agentic_user_id", "agenticUserId")
            ),
        },
    }


def build_activity_context_attachment(
    activity: Any,
    session_id: str = "",
    *,
    manager: dict[str, str] | None = None,
) -> dict[str, Any]:
    context = build_activity_context(activity, session_id)
    manager_context = _build_manager_context(manager)
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Activity context",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": "Sanitized Activity Protocol envelope for this turn.",
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "Small",
                },
                _build_fact_section("User", context["user"]),
                _build_fact_section("Conversation", context["conversation"]),
                _build_fact_section("Digital Worker", context["digitalWorker"]),
                _build_fact_section("Agent Manager", manager_context),
            ],
        },
    }


def _build_manager_context(manager: dict[str, str] | None) -> dict[str, str]:
    if not manager:
        return {
            "displayName": "(unavailable)",
            "userPrincipalName": "(unavailable)",
            "mail": "(unavailable)",
            "meetingDelegateRule": "Only this Digital Worker's current Manager can configure meeting delegation.",
        }
    return {
        "displayName": manager.get("displayName", "") or "(unknown)",
        "userPrincipalName": manager.get("userPrincipalName", "") or "(unknown)",
        "mail": manager.get("mail", "") or "(none)",
        "meetingDelegateRule": "Only this Manager can configure this Digital Worker as a meeting assistant.",
    }


def _build_fact_section(title: str, values: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Large",
        "items": [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Medium",
                "color": "Accent",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": _display_label(key), "value": value}
                    for key, value in values.items()
                ],
            },
        ],
    }


def _display_label(value: str) -> str:
    labels = {
        "displayName": "Display name",
        "userId": "User id",
        "aadObjectId": "AAD object id",
        "sessionId": "Session id",
        "channel": "Channel",
        "conversationId": "Conversation id",
        "conversationType": "Conversation type",
        "locale": "Locale",
        "serviceUrl": "Service URL",
        "channelData": "Channel data",
        "tenantId": "Tenant id",
        "agentAppId": "Agent app id",
        "agentUserId": "Agent user id",
        "userPrincipalName": "User principal name",
        "mail": "Mail",
        "meetingDelegateRule": "Meeting delegate rule",
    }
    return labels.get(value, value)
