"""Adaptive Card rendering for upcoming Calendar meetings."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .meeting_delegate_cards import CONFIGURE_RULES_VERB, SUBMIT_ACTION_KEY


def build_upcoming_meetings_attachment(result: dict[str, Any]) -> dict[str, Any]:
    meetings = result.get("meetings")
    error = str(result.get("error") or "").strip()
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "Upcoming meetings with your Manager",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "Future Calendar meetings attended by both you and your current Manager.",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Small",
        },
    ]
    if error:
        body.append(
            {
                "type": "TextBlock",
                "text": error,
                "color": "Attention",
                "wrap": True,
                "spacing": "Large",
            }
        )
    elif not isinstance(meetings, list) or not meetings:
        body.append(
            {
                "type": "TextBlock",
                "text": "No upcoming meetings with your Manager were found.",
                "wrap": True,
                "spacing": "Large",
            }
        )
    else:
        body.extend(
            _build_meeting_section(meeting)
            for meeting in meetings
            if isinstance(meeting, dict)
        )

    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": body,
        },
    }


def _build_meeting_section(meeting: dict[str, Any]) -> dict[str, Any]:
    time_zone = str(meeting.get("timeZone") or "").strip()
    start = str(meeting.get("start") or "(unknown)").strip()
    end = str(meeting.get("end") or "(unknown)").strip()
    if time_zone:
        start = f"{start} ({time_zone})"
        end = f"{end} ({time_zone})"

    items: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": str(meeting.get("subject") or "Untitled meeting"),
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "spacing": "Medium",
            "facts": [
                {
                    "title": "Meeting ID",
                    "value": str(meeting.get("eventId") or "(unavailable)"),
                },
                {"title": "Start", "value": start},
                {"title": "End", "value": end},
                {
                    "title": "Location",
                    "value": str(meeting.get("location") or "(none)"),
                },
                {
                    "title": "Organizer",
                    "value": str(meeting.get("organizer") or "(unknown)"),
                },
            ],
        },
    ]
    join_web_url = str(meeting.get("joinWebUrl") or "").strip()
    web_link = str(meeting.get("webLink") or "").strip()
    meeting_id = str(meeting.get("eventId") or "").strip()
    actions: list[dict[str, Any]] = []
    if _is_safe_teams_join_url(join_web_url):
        actions.append(
            {
                "type": "Action.OpenUrl",
                "title": "Join Teams meeting",
                "url": join_web_url,
            }
        )
    elif _is_safe_web_link(web_link):
        actions.append(
            {"type": "Action.OpenUrl", "title": "Open meeting", "url": web_link}
        )
    if meeting_id:
        configuration_data = {
            SUBMIT_ACTION_KEY: CONFIGURE_RULES_VERB,
            "meetingId": meeting_id,
            "subject": str(meeting.get("subject") or "").strip(),
            "joinWebUrl": str(meeting.get("joinWebUrl") or "").strip(),
            "scheduledStartTime": str(meeting.get("start") or "").strip(),
            "scheduledEndTime": str(meeting.get("end") or "").strip(),
        }
        actions.append(
            {
                "type": "Action.Submit",
                "title": "Configure replies",
                "data": {
                    **configuration_data,
                    "msteams": {
                        "type": "messageBack",
                        "text": "/submit-meeting-delegate-card",
                        "value": configuration_data,
                    }
                },
            }
        )
    if actions:
        items.append({"type": "ActionSet", "actions": actions})
    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Large",
        "items": items,
    }


def _is_safe_web_link(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_safe_teams_join_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and hostname in {
        "teams.live.com",
        "teams.microsoft.com",
        "teams.microsoft.us",
    }