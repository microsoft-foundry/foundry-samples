"""Trusted Adaptive Card content for the Digital Worker's capabilities."""

from __future__ import annotations

from typing import Any


CAPABILITY_SECTIONS = (
    (
        "Mail",
        "Draft, search, read, send, reply to, and organize email.",
        "Try: Draft an email to Alex about the project update.",
    ),
    (
        "Teams",
        "Find relevant conversations and send messages in Microsoft Teams.",
        "Try: Send Alex a Teams message about tomorrow's review.",
    ),
    (
        "Calendar",
        "Review availability and create or manage calendar events and meetings.",
        "Try: Schedule a 30-minute meeting with Alex tomorrow morning.",
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
                    "text": "How I can help",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        "I can work with your approved Microsoft 365 services "
                        "when you make an explicit request."
                    ),
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "Small",
                },
                *[
                    _build_capability_section(title, description, example)
                    for title, description, example in CAPABILITY_SECTIONS
                ],
                {
                    "type": "TextBlock",
                    "text": (
                        "I will ask for missing recipients, dates, or other "
                        "required details before taking action."
                    ),
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "Medium",
                },
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