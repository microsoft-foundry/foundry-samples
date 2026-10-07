"""Meeting lifecycle and recording-availability notifications."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

from microsoft_agents.activity import Activity
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue
from pydantic import BaseModel, Field

from .workiq import WorkIQError, MeetingWorkIQ
from .meeting_analysis import MeetingAnalysis, source_link_url

logger = logging.getLogger(__name__)
MAX_OCCURRENCES = 20
MAX_TRANSCRIPTS = 8
MAX_SOURCE_CHARS = 120_000
MAX_NOTIFICATION_CHARS = 64_000
ARTIFACT_ATTEMPTS = 3
ARTIFACT_RETRY_SECONDS = 5


def utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Meeting and artifact timestamps must include their timezone.")
    return parsed.astimezone(timezone.utc)


class RecordingAvailable(BaseModel):
    chat_id: str
    started_at: datetime
    viewer_url: str | None = None

    @classmethod
    def from_activity(cls, activity: Activity) -> RecordingAvailable | None:
        text = (activity.text or "").strip()
        if activity.type != "message" or not text.startswith("<URIObject"):
            return None
        if len(text) > MAX_NOTIFICATION_CHARS or "<!DOCTYPE" in text or "<!ENTITY" in text:
            logger.warning("Rejected oversized or DTD-bearing recording notification")
            return None
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            logger.warning("Rejected malformed recording notification XML")
            return None
        status = root.find("RecordingStatus")
        content = root.find("RecordingContent")
        if (
            root.tag != "URIObject"
            or root.get("type") != "Video.2/CallRecording.1"
            or status is None or status.get("status") != "Success"
            or content is None
            or not {"Recording", "Transcript"}.intersection(
                content.get("contentTypes", "").split("+")
            )
        ):
            return None
        # Use the recording's start, not delivery time, to distinguish recurrences.
        timestamp = content.get("timestamp")
        if not timestamp or not activity.conversation or not activity.conversation.id:
            logger.warning("Rejected recording notification without a timestamp or chat")
            return None
        try:
            started_at = utc_time(timestamp)
        except ValueError:
            logger.warning("Rejected recording notification with an invalid timestamp")
            return None
        viewer_url = None
        for item in content.findall("item"):
            uri = item.get("uri")
            if item.get("type") != "onedriveForBusinessVideo" or not uri:
                continue
            try:
                candidate = source_link_url(uri)
                if not (urlsplit(candidate).hostname or "").endswith(".sharepoint.com"):
                    raise ValueError("Recording viewer must be hosted on SharePoint.")
            except ValueError:
                logger.warning("Ignoring invalid recording viewer link; citations will use the meeting chat")
                continue
            viewer_url = candidate
            break
        return cls(
            chat_id=activity.conversation.id, started_at=started_at, viewer_url=viewer_url,
        )


class Occurrence(BaseModel):
    meeting_id: str
    event_id: str
    chat_id: str
    join_url: str
    started_at: datetime
    ended_at: datetime | None = None
    artifacts_available: bool = False
    viewer_url: str | None = None
    agenda: list[str] = Field(default_factory=list)
    reminder: Literal["unsent", "reserved", "sent"] = "unsent"
    recap: Literal["unsent", "reserved", "sent"] = "unsent"
    pending_notice: Literal["unsent", "reserved", "sent"] = "unsent"


class MeetingState(BaseModel):
    occurrences: dict[str, Occurrence] = Field(default_factory=dict)


SaveState = Callable[[], Awaitable[None]]
PostMessage = Callable[[str], Awaitable[object]]


class MeetingLifecycle:
    def __init__(
        self, state: MeetingState, workiq: MeetingWorkIQ, analysis: MeetingAnalysis,
        save: SaveState, post: PostMessage,
    ):
        self.state = state
        self.workiq = workiq
        self.analysis = analysis
        self.save = save
        self.post = post

    async def _post_once(self, record: Occurrence, field: str, message: str) -> None:
        if getattr(record, field) != "unsent":
            logger.info("Suppressing replay or uncertain delivery for meeting %s", field)
            return
        # Persist before the side effect. A crash may lose delivery, but must not
        # blindly repeat a possibly successful chat post.
        setattr(record, field, "reserved")
        await self.save()
        await self.post(message)
        setattr(record, field, "sent")
        await self.save()

    async def start(self, meeting: MeetingStartEventValue, chat_id: str) -> None:
        join_url = meeting.join_url.strip()
        started_at = utc_time(meeting.start_time.isoformat())
        key = hashlib.sha256(
            f"{chat_id}\n{join_url}\n{started_at.isoformat()}".encode()
        ).hexdigest()
        if key in self.state.occurrences:
            logger.info("Ignoring repeated meeting start")
            return
        if len(self.state.occurrences) >= MAX_OCCURRENCES:
            raise ValueError("Meeting state reached its occurrence limit; administrator cleanup is required.")
        if any(
            record.ended_at is None and record.chat_id == chat_id
            for record in self.state.occurrences.values()
        ):
            raise ValueError("A previous meeting start has no end; cannot safely select this occurrence.")
        online_meeting = await self.workiq.meeting_in_chat(join_url, chat_id)
        event = await self.workiq.invited_event(join_url, started_at)
        body = (event.get("body") or {}).get("content") or ""
        agenda = await self.analysis.extract_agenda(body) if body.strip() else []
        record = Occurrence(
            meeting_id=online_meeting["id"], event_id=event["id"],
            chat_id=chat_id, join_url=join_url,
            started_at=started_at, agenda=agenda,
        )
        self.state.occurrences[key] = record
        await self.save()
        if not agenda:
            logger.info("No explicit agenda found; skipping meeting reminder and closure report")
            return
        text = "**Agenda reminder**\n\n" + "\n".join(
            f"{index}. {item}" for index, item in enumerate(agenda, 1)
        )
        await self._post_once(record, "reminder", text)

    async def end(self, meeting: MeetingEndEventValue, chat_id: str) -> None:
        join_url = meeting.join_url.strip()
        ended_at = utc_time(meeting.end_time.isoformat())
        same_meeting = [
            record for record in self.state.occurrences.values()
            if record.chat_id == chat_id and record.join_url == join_url
        ]
        if any(record.ended_at == ended_at for record in same_meeting):
            logger.info("Ignoring repeated meeting end; pending artifacts use availability notifications")
            return
        matches = [
            record for record in same_meeting
            if record.ended_at is None
            and timedelta(0) <= ended_at - record.started_at <= timedelta(hours=24)
        ]
        if len(matches) != 1:
            raise ValueError("No unique recorded start matches this end; no agenda snapshot is available.")
        record = matches[0]
        record.ended_at = ended_at
        await self.save()
        if record.agenda:
            await self._post_once(
                record, "pending_notice",
                "The meeting has ended. I'll prepare meeting notes and share them here once "
                "the transcript is available. I'll retry automatically when Teams reports "
                "that the recording or transcript is ready.",
            )
        if record.artifacts_available:
            await self._process_available(record)
        else:
            await self.process_pending(record)

    async def recording_available(self, signal: RecordingAvailable) -> None:
        records = [
            record for record in self.state.occurrences.values()
            if record.chat_id == signal.chat_id
            and record.started_at <= signal.started_at <= (
                record.ended_at or record.started_at + timedelta(hours=24)
            )
        ]
        if not records:
            logger.info("Ignoring recording availability without a matching observed meeting")
            return
        if len(records) != 1:
            raise ValueError("Recording notification matches more than one observed occurrence.")
        record = records[0]
        if not record.artifacts_available or (
            signal.viewer_url is not None and signal.viewer_url != record.viewer_url
        ):
            record.artifacts_available = True
            if signal.viewer_url is not None:
                record.viewer_url = signal.viewer_url
            await self.save()
        if record.ended_at is None:
            logger.info("Recording is available; waiting for the meeting-end event")
            return
        await self._process_available(record)

    async def _process_available(self, record: Occurrence) -> None:
        for attempt in range(ARTIFACT_ATTEMPTS):
            try:
                if await self.process_pending(record):
                    return
            except WorkIQError as error:
                if error.status != 404:
                    raise
                logger.warning(
                    "Meeting artifacts not yet readable after notification (Work IQ 404): "
                    "code=%s inner_code=%s request_id=%s diagnostics=%s",
                    error.code, error.inner_code, error.request_id,
                    json.dumps(error.diagnostic_fields(), sort_keys=True),
                )
            if attempt < ARTIFACT_ATTEMPTS - 1:
                await asyncio.sleep(ARTIFACT_RETRY_SECONDS)
        logger.warning("Artifacts remain unavailable after notification retries; report is still pending")

    async def process_pending(self, record: Occurrence) -> bool:
        if record.ended_at is None:
            raise ValueError("Cannot create a closure report before an observed meeting end.")
        if not record.agenda or record.recap != "unsent":
            logger.info("No pending agenda closure report for this occurrence")
            return True
        meeting = await self.workiq.meeting_in_chat(record.join_url, record.chat_id)
        if meeting["id"] != record.meeting_id:
            raise ValueError("The meeting binding changed; refusing to post artifacts to this chat.")
        listing = await self.workiq.list_transcripts(record.meeting_id)
        if listing["has_more"]:
            raise ValueError("Transcript listing is incomplete; cannot safely compare this occurrence.")
        transcripts = []
        for item in listing["items"]:
            if not item.get("createdDateTime"):
                raise ValueError("A transcript lacks occurrence timestamps; refusing to guess.")
            started = utc_time(item["createdDateTime"])
            ended = utc_time(item.get("endDateTime") or item["createdDateTime"])
            if record.started_at <= started <= ended <= record.ended_at + timedelta(minutes=5):
                transcripts.append(item)
        if not transcripts:
            await self._post_once(
                record, "pending_notice",
                "The meeting has ended, but its transcript is not ready or cannot yet be matched "
                "to this occurrence. I'll retry automatically when Teams reports that the recording "
                "or transcript is available.",
            )
            return False
        if len(transcripts) > MAX_TRANSCRIPTS:
            raise ValueError("Too many transcript segments for a complete report in this sample.")
        sources = {}
        for item in transcripts:
            transcript = await self.workiq.get_transcript(record.meeting_id, item["id"])
            sources[f"transcript:{item['id']}"] = transcript["content"]
        if sum(len(content) for content in sources.values()) > MAX_SOURCE_CHARS:
            raise ValueError("Meeting artifacts exceed the complete-analysis limit; no partial closure report was posted.")
        viewer_url = record.viewer_url if len(transcripts) == 1 else None
        source_url = viewer_url or (
            f"https://teams.microsoft.com/l/chat/{quote(record.chat_id, safe='')}/conversations"
        )
        report = await self.analysis.compare(record.agenda, sources, source_url=source_url)
        source_note = (
            "Source links open the recording/transcript viewer."
            if viewer_url else
            "Source links open the meeting chat. Select Recap to view the transcript."
        )
        await self._post_once(record, "recap", f"{report}\n\n{source_note}")
        return True
