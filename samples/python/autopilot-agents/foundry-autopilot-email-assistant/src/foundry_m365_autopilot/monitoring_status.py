"""Adaptive Card rendering for forwarded-email monitoring status."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any


def build_monitoring_status_attachment(result: dict[str, Any]) -> dict[str, Any]:
    error = result.get("error") if isinstance(result, dict) else None
    if isinstance(error, dict):
        return _build_error_attachment(str(error.get("message") or "Unable to read configuration."))

    enabled = result.get("enabled") is True
    manager = result.get("currentManager")
    manager = manager if isinstance(manager, dict) else {}
    manager_name = str(
        manager.get("displayName")
        or manager.get("userPrincipalName")
        or "Current Manager"
    )
    manager_upn = str(manager.get("userPrincipalName") or manager.get("mail") or "Not available")

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "Email monitoring",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "ON" if enabled else "OFF",
            "weight": "Bolder",
            "color": "Good" if enabled else "Attention",
            "spacing": "Small",
        },
        {
            "type": "TextBlock",
            "text": (
                "Forwarded messages are checked against your active rule."
                if enabled
                else "Forwarded messages are not being monitored."
            ),
            "isSubtle": True,
            "wrap": True,
            "spacing": "Small",
        },
        _fact_section(
            "Owner",
            [
                ("Manager", manager_name),
                ("Account", manager_upn),
            ],
        ),
    ]

    if enabled:
        body.append(
            _text_section(
                "Active rule",
                str(result.get("filterDescription") or "No rule description available."),
            )
        )
        source_text = str(result.get("sourceText") or "").strip()
        if source_text:
            body.append(_text_section("Original request", source_text, subtle=True))
        body.append(
            _fact_section(
                "Details",
                [("Last updated", str(result.get("updatedAt") or "Not available"))],
            )
        )

    reason = str(result.get("reason") or "").strip()
    if reason:
        body.append(_text_section("Why it is off", reason))

    body.append(_config_section(result.get("config")))
    body.append(
        {
            "type": "TextBlock",
            "text": "Keep the Exchange forwarding rule enabled for matching messages to reach this assistant.",
            "wrap": True,
            "isSubtle": True,
            "separator": True,
            "spacing": "Large",
        }
    )
    return _attachment(body)


def build_monitoring_configuration_attachment(
    result: dict[str, Any],
) -> dict[str, Any]:
    return _attachment(
        [
            {
                "type": "TextBlock",
                "text": "Email monitoring enabled",
                "weight": "Bolder",
                "size": "Large",
                "color": "Good",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "Your monitoring rule has been saved and is active.",
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
            },
            _text_section(
                "Active rule",
                str(result.get("filterDescription") or "Rule configured."),
            ),
            _text_section(
                "Original request",
                str(result.get("sourceText") or "Not available"),
                subtle=True,
            ),
            {
                "type": "TextBlock",
                "text": "Keep your Exchange forwarding rule enabled. Matching forwarded messages will be evaluated by this assistant.",
                "wrap": True,
                "isSubtle": True,
                "separator": True,
                "spacing": "Large",
            },
        ]
    )


def build_monitoring_clarification_attachment(message: str) -> dict[str, Any]:
    text = _plain_text(message)
    return _attachment(
        [
            {
                "type": "TextBlock",
                "text": "Complete your monitoring rule",
                "weight": "Bolder",
                "size": "Large",
                "color": "Accent",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "I need one more detail before saving the rule.",
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
            },
            _text_section("Please confirm", text or "Please provide the missing rule details."),
            {
                "type": "TextBlock",
                "text": "Reply in the chat with your choice or corrected condition.",
                "wrap": True,
                "isSubtle": True,
                "separator": True,
                "spacing": "Large",
            },
        ]
    )


def _fact_section(title: str, facts: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Large",
        "items": [
            _section_title(title),
            {
                "type": "FactSet",
                "spacing": "Small",
                "facts": [{"title": label, "value": value} for label, value in facts],
            },
        ],
    }


def _text_section(title: str, text: str, *, subtle: bool = False) -> dict[str, Any]:
    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Large",
        "items": [
            _section_title(title),
            {
                "type": "TextBlock",
                "text": text,
                "wrap": True,
                "isSubtle": subtle,
                "spacing": "Small",
            },
        ],
    }


def _section_title(title: str) -> dict[str, Any]:
    return {
        "type": "TextBlock",
        "text": title,
        "weight": "Bolder",
        "color": "Accent",
        "wrap": True,
    }


def _config_section(config: Any) -> dict[str, Any]:
    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Large",
        "items": [
            _section_title("Config"),
            {
                "type": "ActionSet",
                "spacing": "Small",
                "actions": [
                    {
                        "type": "Action.ToggleVisibility",
                        "title": "Show/hide raw JSON",
                        "targetElements": ["monitoring-config-json"],
                    }
                ],
            },
            {
                "type": "TextBlock",
                "id": "monitoring-config-json",
                "text": json.dumps(
                    config,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
                "fontType": "Monospace",
                "wrap": True,
                "isVisible": False,
                "spacing": "Medium",
            },
        ],
    }


def _build_error_attachment(message: str) -> dict[str, Any]:
    return _attachment(
        [
            {
                "type": "TextBlock",
                "text": "Email monitoring unavailable",
                "weight": "Bolder",
                "size": "Large",
                "color": "Attention",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": message,
                "wrap": True,
                "spacing": "Medium",
            },
        ]
    )


def _attachment(body: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": body,
        },
    }


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "li", "p", "ul", "ol"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"li", "p"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(re.sub(r"```(?:html)?|```", "", str(value or ""), flags=re.IGNORECASE))
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)