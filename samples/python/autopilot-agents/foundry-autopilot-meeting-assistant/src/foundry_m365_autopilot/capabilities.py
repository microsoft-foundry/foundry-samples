"""Trusted Adaptive Card content for the Meeting Assistant's capabilities."""

from __future__ import annotations

from typing import Any


CAPABILITY_SECTIONS = (
    (
        "Delegated meeting lookup",
        "Find future meetings the Agent has been added to attend on behalf of their Manager.",
        "Try: /meeting",
    ),
    (
        "Meeting-chat responses",
        "Detect mentions in Teams meeting chat and answer only from pre-approved rules.",
        "Try: Ask the Digital Worker an approved question in meeting chat.",
    ),
)

def build_capabilities_attachment() -> dict[str, Any]:
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "How I can help with meetings",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": "I act within Manager-approved meeting-chat rules.",
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "Small",
                },
                *[
                    _build_capability_section(title, description, example)
                    for title, description, example in CAPABILITY_SECTIONS
                ],
            ],
        },
    }


def _build_capability_section(
    title: str, description: str, example: str
) -> dict[str, Any]:
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
                "type": "TextBlock",
                "text": description,
                "wrap": True,
                "spacing": "Small",
            },
            {
                "type": "TextBlock",
                "text": example,
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
            },
        ],
    }