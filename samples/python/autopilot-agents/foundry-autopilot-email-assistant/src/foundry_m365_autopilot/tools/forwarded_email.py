# Copyright (c) Microsoft. All rights reserved.

"""Parsing and filter-context helpers for forwarded-email monitoring."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import quote

from microsoft_agents.hosting.core import TurnContext

MAX_SUMMARY_CHARS = 50
_INVALID_SUMMARY_PATTERNS = (
    r"\bi(?:'m| am) sorry\b.*\b(?:cannot|can't|unable to) assist\b",
    r"\bi (?:cannot|can't|am unable to) (?:assist|help|comply)\b",
    r"\b(?:cannot|can't|unable to) (?:assist|help|comply) with that request\b",
    r"^i encountered an error processing your request\b",
    r"^http status:\s*\d+\b",
)


class _HtmlTextExtractor(HTMLParser):
    _BLOCK_TAGS = frozenset(
        {"br", "div", "p", "li", "tr", "table", "blockquote", "hr"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        value = "".join(self._parts).replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.strip() for line in value.splitlines())


def get_activity_sender_address(context: TurnContext) -> str:
    activity = getattr(context, "activity", None)
    sender = getattr(activity, "from_property", None)
    for name in ("id", "email", "user_principal_name"):
        value = str(getattr(sender, name, "") or "").strip()
        if "@" in value:
            return value
    return ""


def parse_forwarded_email(html_body: str) -> Optional[dict[str, str]]:
    """Parse an English Outlook forwarded-header block from HTML or plain text."""

    if not html_body.strip():
        return None
    header_pattern = re.compile(
        r"(?ims)^\s*From:\s*(?P<from>[^\n]+)\n"
        r"(?:.*?\n){0,8}?\s*(?:Sent|Date):\s*(?P<sent>[^\n]*)\n"
        r"(?:.*?\n){0,8}?\s*To:\s*[^\n]*\n"
        r"(?:.*?\n){0,8}?\s*Subject:\s*(?P<subject>[^\n]*)\n"
    )
    address_pattern = re.compile(
        r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        flags=re.IGNORECASE,
    )
    plain_text = html_body.replace("\r\n", "\n").replace("\r", "\n")
    parser = _HtmlTextExtractor()
    parser.feed(html_body)
    for text in (plain_text, parser.text()):
        match = header_pattern.search(text)
        if not match:
            continue
        addresses = address_pattern.findall(match.group("from"))
        if not addresses:
            continue
        return {
            "sender": addresses[-1],
            "subject": match.group("subject").strip(),
            "body": text[match.end():].strip(),
            "sentAt": normalize_forwarded_sent_at(match.group("sent")),
        }
    return None


def normalize_forwarded_sent_at(value: str) -> str:
    """Best-effort normalization of common Outlook forwarded-date formats."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        offset_match = re.search(r"\(UTC(?P<offset>[+-]\d{2}:\d{2})\)", raw)
        without_offset = re.sub(r"\s*\(UTC[+-]\d{2}:\d{2}\)\s*$", "", raw)
        parsed = None
        for pattern in (
            "%A, %B %d, %Y %I:%M:%S %p",
            "%A, %B %d, %Y %I:%M %p",
            "%B %d, %Y",
            "%A, %m/%d/%Y %I:%M:%S %p",
            "%A, %m/%d/%Y %I:%M %p",
            "%a, %m/%d/%Y %I:%M:%S %p",
            "%a, %m/%d/%Y %I:%M %p",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y",
        ):
            try:
                parsed = datetime.strptime(without_offset, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            return ""
        if offset_match:
            sign = 1 if offset_match.group("offset").startswith("+") else -1
            hours, minutes = offset_match.group("offset")[1:].split(":")
            parsed = parsed.replace(
                tzinfo=timezone(
                    sign * timedelta(hours=int(hours), minutes=int(minutes))
                )
            )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_mail_filter_context(
    forwarded: dict[str, str], context: TurnContext
) -> dict[str, Any]:
    activity = getattr(context, "activity", None)
    raw_importance = getattr(activity, "importance", "") or ""
    importance = str(getattr(raw_importance, "value", raw_importance)).lower()
    if not importance:
        channel_data = getattr(activity, "channel_data", None)
        if isinstance(channel_data, dict):
            importance = str(channel_data.get("importance") or "").lower()
    if importance not in {"low", "normal", "high"}:
        importance = ""
    return {
        "originalSender": {"address": forwarded.get("sender", "").casefold()},
        "subject": forwarded.get("subject", ""),
        "body": {"text": forwarded.get("body", "")},
        "sentAt": forwarded.get("sentAt", ""),
        "importance": importance,
    }


def normalize_mail_summary(value: str) -> str:
    """Flatten and enforce the display limit for a model-generated summary."""

    summary = re.sub(r"\s+", " ", str(value or "")).strip().strip('"“”')
    if not summary or any(
        re.search(pattern, summary, flags=re.IGNORECASE)
        for pattern in _INVALID_SUMMARY_PATTERNS
    ):
        return "Summary unavailable. Open the email for details."
    return summary[:MAX_SUMMARY_CHARS]


def build_manager_notification(
    forwarded: dict[str, str],
    summary: str,
) -> dict[str, Any]:
    """Build the fixed Adaptive Card used for matched-mail notifications."""

    sender = str(forwarded.get("sender") or "").strip()
    subject = str(forwarded.get("subject") or "").strip()
    search_terms = []
    if sender:
        search_terms.append(f'from:"{sender}"')
    if subject:
        search_terms.append(f'subject:"{subject}"')
    search_query = " ".join(search_terms) or subject or sender
    message_url = (
        "https://outlook.office.com/mail/search?q="
        f"{quote(search_query, safe='')}"
    )
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Matched monitored email",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": "Attention",
                    "wrap": True,
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {
                            "title": "Original sender",
                            "value": sender or "(Unknown)",
                        },
                        {
                            "title": "Subject",
                            "value": subject or "(No subject)",
                        },
                        {
                            "title": "Sent time",
                            "value": str(forwarded.get("sentAt") or "(Unknown)"),
                        },
                    ],
                },
                {
                    "type": "TextBlock",
                    "text": "AI summary",
                    "weight": "Bolder",
                    "spacing": "Medium",
                },
                {
                    "type": "TextBlock",
                    "text": normalize_mail_summary(summary),
                    "wrap": True,
                    "spacing": "Small",
                },
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Find email in Outlook",
                    "url": str(message_url),
                }
            ],
        },
    }
