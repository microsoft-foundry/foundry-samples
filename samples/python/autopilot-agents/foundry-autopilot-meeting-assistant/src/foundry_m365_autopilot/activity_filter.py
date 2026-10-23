"""Filters for Activity Protocol messages that must not reach the model."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class ActivityDeduplicator:
    def __init__(self, ttl_seconds: float = 300, max_entries: int = 2048) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._seen: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, activity: Any) -> bool:
        activity_id = str(_get_value(activity, "id") or "").strip()
        if not activity_id:
            return False

        now = time.monotonic()
        cutoff = now - self._ttl_seconds
        while self._seen:
            oldest_id, oldest_time = next(iter(self._seen.items()))
            if oldest_time >= cutoff:
                break
            self._seen.pop(oldest_id)

        previous_time = self._seen.get(activity_id)
        if previous_time is not None and previous_time >= cutoff:
            self._seen.move_to_end(activity_id)
            return True

        self._seen[activity_id] = now
        self._seen.move_to_end(activity_id)
        while len(self._seen) > self._max_entries:
            self._seen.popitem(last=False)
        return False


def is_agent_authored_activity(activity: Any) -> bool:
    sender = _get_value(activity, "from_property", "from")
    recipient = _get_value(activity, "recipient")
    sender_ids = _identity_values(sender)
    recipient_ids = _identity_values(recipient)
    return bool(sender_ids and recipient_ids and sender_ids.intersection(recipient_ids))


def _identity_values(identity: Any) -> set[str]:
    values = {
        _get_value(identity, "id"),
        _get_value(identity, "aad_object_id", "aadObjectId"),
        _get_value(identity, "agentic_app_id", "agenticAppId"),
        _get_value(identity, "agentic_user_id", "agenticUserId"),
    }
    return {str(value).strip().casefold() for value in values if value}


def _get_value(value: Any, *names: str) -> Any:
    if isinstance(value, dict):
        for name in names:
            result = value.get(name)
            if result is not None:
                return result
        return None
    for name in names:
        result = getattr(value, name, None)
        if result is not None:
            return result
    return None