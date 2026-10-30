# Copyright (c) Microsoft. All rights reserved.

"""Classification helpers for Microsoft 365 channel activities."""

from __future__ import annotations

from typing import Any

from microsoft_agents.activity import Activity

_AGENTS_CHANNEL = "agents"
_EMAIL_CHANNEL = "email"


def is_email_notification(notification_activity: Any) -> bool:
    notification_type = getattr(notification_activity, "notification_type", None)
    value = getattr(notification_type, "value", notification_type)
    return "email" in str(value or "").lower()


def is_email_activity(activity: Activity | None) -> bool:
    if activity is None:
        return False

    channel, sub_channel = _split_channel_id(getattr(activity, "channel_id", None))
    if channel == _EMAIL_CHANNEL or (
        channel == _AGENTS_CHANNEL and sub_channel == _EMAIL_CHANNEL
    ):
        return True

    return _get_product_id(activity) == _EMAIL_CHANNEL


def _split_channel_id(channel_id: Any) -> tuple[str, str]:
    if channel_id is None:
        return "", ""

    channel = str(getattr(channel_id, "channel", "") or "")
    sub_channel = str(getattr(channel_id, "sub_channel", "") or "")
    if not channel:
        value = str(channel_id)
        channel, _, sub_channel = value.partition(":")

    return channel.lower(), sub_channel.lower()


def _get_product_info(activity: Activity) -> Any:
    get_product_info_entity = getattr(activity, "get_product_info_entity", None)
    if not callable(get_product_info_entity):
        return None
    return get_product_info_entity()


def _get_product_id(activity: Activity) -> str:
    product_info = _get_product_info(activity)
    product_id = _get_first_value(product_info, "id")
    if product_id:
        return str(product_id).lower()

    for entity in getattr(activity, "entities", None) or []:
        if _entity_type(entity) == "productinfo":
            return str(_get_first_value(entity, "id") or "").lower()

    return ""


def _entity_type(entity: Any) -> str:
    return str(_get_first_value(entity, "type") or "").lower()


def _get_first_value(value: Any, *names: str) -> Any:
    if value is None:
        return ""

    if isinstance(value, dict):
        lower_map = {str(key).lower(): item for key, item in value.items()}
        for name in names:
            item = value.get(name)
            if item is not None and item != "":
                return item
            item = lower_map.get(name.lower())
            if item is not None and item != "":
                return item
        return ""

    for name in names:
        item = getattr(value, name, None)
        if item is not None and item != "":
            return item
    return ""
