"""Trusted Adaptive Card content for the Email Assistant's capabilities."""

from __future__ import annotations

from typing import Any


CAPABILITY_SECTIONS = (
    (
        "Agent User mailbox",
        "Read, search, send, and reply to mail in the Digital Worker's mailbox.",
        "Try: Show my latest five messages.",
    ),
    (
        "Delegated mailbox",
        "Read the Inbox of an explicitly named mailbox that granted access.",
        "Try: Read the latest messages from owner@contoso.com.",
    ),
    (
        "Forwarded-email monitoring",
        "Save a Manager-approved rule and evaluate email forwarded by that Manager.",
        "Try: Notify me when I forward an urgent customer email.",
    ),
    (
        "Teams notifications",
        "Proactively notify the Manager in Teams when forwarded mail matches the rule.",
        "Try: Show my current mail monitoring status.",
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
                    "text": "How I can help with email",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": "I use approved mailbox access and Manager-owned rules.",
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
