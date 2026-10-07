"""Synthetic meeting lifecycle events; no live Teams delivery is implied."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from microsoft_agents.activity import ResourceResponse
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage, TurnContext
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue
from microsoft_teams.api.models import ChannelData

from agent.app import (
    MeetingHandlers, is_added_to_meeting, is_supported_teams_group_chat,
    is_recording_available, register_handlers, get_meeting_conversation_id,
)
from agent.workiq import WorkIQDiagnostics, WorkIQError
from agent.meeting_lifecycle import (
    MeetingLifecycle, MeetingState, RecordingAvailable,
)
from test_meeting_assistant import AGENT_USER, SETTINGS, TENANT, USER, INSTANCE, activity

START = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)
END = START + timedelta(hours=1)
START_EVENT = "application/vnd.microsoft.meetingStart"
END_EVENT = "application/vnd.microsoft.meetingEnd"
CHAT = "19:meeting@thread.v2"
JOIN = "https://teams.microsoft.com/l/meetup-join/synthetic"


def meeting_args(kind="start", when=None, chat_id=CHAT, join_url=JOIN):
    event = meeting_activity(kind)
    event.value["JoinUrl"] = join_url
    field = "StartTime" if kind == "start" else "EndTime"
    event.value[field] = (when or (START if kind == "start" else END)).isoformat()
    model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
    return model.model_validate(event.value), chat_id


def meeting_activity(kind="start", *, pascal_case=True, **overrides):
    values = {
        "type": "event",
        "name": START_EVENT if kind == "start" else END_EVENT,
        "conversation": {"id": CHAT, "isGroup": True, "tenantId": TENANT},
        "value": {
            "Id": "synthetic-meeting", "Title": "Planning",
            "MeetingType": "Scheduled", "JoinUrl": JOIN,
            "StartTime" if kind == "start" else "EndTime":
                (START if kind == "start" else END).isoformat(),
        },
    }
    if not pascal_case:
        values["value"] = {key[0].lower() + key[1:]: value for key, value in values["value"].items()}
    values.update(overrides)
    return activity(**values)


def recording_signal(*, when=None, chat_id=CHAT):
    return RecordingAvailable(chat_id=chat_id, started_at=when or START + timedelta(minutes=1))


def recording_activity(*, status="Success", content_types="Recording+Transcript", when=None, **overrides):
    timestamp = (when or START + timedelta(minutes=1)).isoformat()
    values = {
        "type": "message", "textFormat": "plain",
        "conversation": {"id": CHAT, "isGroup": True, "conversationType": "groupChat", "tenantId": TENANT},
        "channelData": {"tenant": {"id": TENANT}, "meeting": {"id": "synthetic-meeting"}},
        "text": (
            '<URIObject format_version="1.1" type="Video.2/CallRecording.1" version="1.0">'
            f'<RecordingStatus status="{status}" code="200" />'
            '<Title>Planning</Title>'
            f'<RecordingContent contentTypes="{content_types}" timestamp="{timestamp}" duration="0:00:37.4">'
            '<item type="onedriveForBusinessTranscript" uri="https://example.test/not-followed" />'
            '</RecordingContent></URIObject>'
        ),
    }
    values.update(overrides)
    return activity(**values)


def meeting_added_activity(**overrides):
    values = {
        "type": "conversationUpdate",
        "conversation": {"id": CHAT, "isGroup": True, "conversationType": "groupChat", "tenantId": TENANT},
        "membersAdded": [{"id": f"8:orgid:{AGENT_USER}"}],
        "channelData": {"tenant": {"id": TENANT}, "source": None, "meeting": {"id": "synthetic-meeting"}},
    }
    values.update(overrides)
    event = activity(**values)
    event.recipient.id = f"8:orgid:{AGENT_USER}"
    return event


class EventContractTests(TestCase):
    def test_non_lifecycle_selectors_accept_sdk_typed_channel_data(self):
        for event, selector in (
            (meeting_added_activity(), is_added_to_meeting),
            (recording_activity(), is_recording_available),
        ):
            event.channel_data = ChannelData.model_validate(event.channel_data)
            self.assertTrue(is_supported_teams_group_chat(event))
            self.assertTrue(selector(event))

    def test_agent_added_to_meeting_uses_sdk_membership_and_channel_data(self):
        event = meeting_added_activity()
        self.assertTrue(is_added_to_meeting(event))
        self.assertNotIn("eventType", event.channel_data)
        event.members_added.append(event.recipient)
        self.assertTrue(is_added_to_meeting(event))

    def test_unrelated_conversation_updates_are_not_meeting_additions(self):
        for event in (
            meeting_added_activity(membersAdded=[]),
            meeting_added_activity(membersAdded=[{"id": f"8:orgid:{USER}"}]),
            meeting_added_activity(membersAdded=[{"id": AGENT_USER}]),
            meeting_added_activity(type="message"),
            meeting_added_activity(channelData={"tenant": {"id": TENANT}}),
            meeting_added_activity(channelData={"meeting": None}),
            meeting_added_activity(channelData={"meeting": {}}),
            meeting_added_activity(channelData={"meeting": {"id": " "}}),
            meeting_added_activity(channelId="emulator"),
            meeting_added_activity(conversation={"id": CHAT, "conversationType": "channel", "isGroup": True}),
            meeting_added_activity(channelData={"tenant": {"id": INSTANCE}, "meeting": {"id": "meeting"}}),
        ):
            self.assertFalse(is_added_to_meeting(event))
        event = meeting_added_activity()
        event.recipient.id = ""
        self.assertFalse(is_added_to_meeting(event))

    def test_malformed_meeting_metadata_is_logged(self):
        for meeting in ("not-an-object", {"id": 123}):
            with self.assertLogs("agent.app", level="WARNING"):
                self.assertFalse(is_added_to_meeting(meeting_added_activity(channelData={"meeting": meeting})))

    def test_native_models_reject_unsupported_camel_case_wire_fields(self):
        for kind in ("start", "end"):
            event = meeting_activity(kind, pascal_case=False)
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            with self.assertRaises(ValueError):
                model.model_validate(event.value)

    def test_captured_pascal_case_parses_without_mutating_the_payload(self):
        for kind in ("start", "end"):
            event = meeting_activity(kind)
            original_value = dict(event.value)
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            parsed = model.model_validate(event.value)
            self.assertEqual(get_meeting_conversation_id(event, parsed), CHAT)
            timestamp = parsed.start_time if kind == "start" else parsed.end_time
            self.assertEqual(timestamp, START if kind == "start" else END)
            self.assertEqual(parsed.join_url, JOIN)
            self.assertEqual(event.value, original_value)

    def test_native_timestamps_keep_the_original_offset_during_validation(self):
        for kind in ("start", "end"):
            event = meeting_activity(kind)
            field = "StartTime" if kind == "start" else "EndTime"
            event.value[field] = "2026-10-01T16:00:00+02:00"
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            parsed = model.model_validate(event.value)
            original = parsed.model_dump()
            self.assertEqual(get_meeting_conversation_id(event, parsed), CHAT)
            timestamp = parsed.start_time if kind == "start" else parsed.end_time
            self.assertEqual(timestamp, START)
            self.assertEqual(timestamp.utcoffset(), timedelta(hours=2))
            self.assertEqual(parsed.model_dump(), original)

    def test_native_fields_are_validated_without_mutating_the_sdk_model(self):
        event = meeting_activity()
        event.value.update(MeetingType=" Scheduled ", JoinUrl=f" {JOIN} ")
        parsed = MeetingStartEventValue.model_validate(event.value)
        original = parsed.model_dump()
        self.assertEqual(get_meeting_conversation_id(event, parsed), CHAT)
        self.assertEqual(parsed.join_url, f" {JOIN} ")
        self.assertEqual(parsed.model_dump(), original)

    def test_sdk_rejects_missing_common_fields(self):
        for kind in ("start", "end"):
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            for field in ("Id", "Title", "MeetingType", "JoinUrl", "StartTime" if kind == "start" else "EndTime"):
                event = meeting_activity(kind)
                event.value.pop(field)
                with self.assertRaises(ValueError):
                    model.model_validate(event.value)

    def test_sdk_controls_alias_selection_without_raw_payload_checks(self):
        for kind in ("start", "end"):
            event = meeting_activity(kind)
            event.value.update(id="extra-id", joinUrl="https://example.test/extra")
            original = event.value.copy()
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            parsed = model.model_validate(event.value)
            self.assertEqual(get_meeting_conversation_id(event, parsed), CHAT)
            self.assertEqual(parsed.id, event.value["Id"])
            self.assertEqual(parsed.join_url, JOIN)
            self.assertEqual(event.value, original)

    def test_empty_fields_and_invalid_timestamps_are_rejected(self):
        for kind in ("start", "end"):
            model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
            for field in ("Id", "Title", "MeetingType", "JoinUrl"):
                for value in (" ", None, 123):
                    event = meeting_activity(kind)
                    event.value[field] = value
                    with self.assertRaises(ValueError):
                        get_meeting_conversation_id(event, model.model_validate(event.value))
            for value in (None, "not-a-time", "2026-10-02T20:48:16"):
                event = meeting_activity(kind)
                event.value["StartTime" if kind == "start" else "EndTime"] = value
                with self.assertRaises(ValueError):
                    get_meeting_conversation_id(event, model.model_validate(event.value))

    def test_lifecycle_requires_consistent_identity_and_meeting_chat(self):
        self.assertFalse(is_supported_teams_group_chat(meeting_activity(conversation={
            "id": CHAT, "isGroup": True, "tenantId": INSTANCE,
        })))
        self.assertFalse(is_supported_teams_group_chat(meeting_activity(conversation={
            "id": CHAT, "conversationType": "channel", "isGroup": True, "tenantId": TENANT,
        })))
        for recipient in ({"role": "bot"}, {"role": "agenticUser", "agenticAppId": INSTANCE}):
            self.assertFalse(is_supported_teams_group_chat(meeting_activity(recipient=recipient)))
        self.assertFalse(is_supported_teams_group_chat(meeting_activity(channelId="emulator")))

    def test_no_configured_tenant_gate(self):
        event = meeting_activity()
        event.recipient.tenant_id = INSTANCE
        event.conversation.tenant_id = INSTANCE
        self.assertTrue(is_supported_teams_group_chat(event))

    def test_tenant_in_channel_data_routes_both_meeting_events(self):
        for kind in ("start", "end"):
            event = meeting_activity(
                kind, conversation={"id": CHAT, "isGroup": True},
                channelData={"tenant": {"id": TENANT}},
            )
            self.assertIsNone(event.conversation.tenant_id)
            self.assertTrue(is_supported_teams_group_chat(event))

    def test_conflicting_or_invalid_channel_tenant_is_rejected(self):
        for tenant in ({"id": INSTANCE}, {"id": 123}, "invalid"):
            with self.subTest(tenant=tenant):
                self.assertFalse(is_supported_teams_group_chat(
                    meeting_activity(channelData={"tenant": tenant}),
                ))
        self.assertFalse(is_supported_teams_group_chat(meeting_activity(
            conversation={"id": CHAT, "isGroup": True},
        )))

    def test_missing_time_and_scheduled_calendar_data_are_not_events(self):
        for value in (
            {"meetingType": "Scheduled", "joinUrl": JOIN},
            {"meetingType": "Scheduled", "joinUrl": JOIN, "startTime": "2026-10-01T14:00:00"},
            {"meetingType": "Channel", "joinUrl": JOIN, "startTime": START.isoformat()},
        ):
            with self.assertRaises(ValueError):
                MeetingStartEventValue.model_validate(value)

    def test_missing_chat_id_is_rejected(self):
        event = meeting_activity()
        event.conversation = None
        with self.assertRaisesRegex(ValueError, "conversation ID"):
            get_meeting_conversation_id(event, MeetingStartEventValue.model_validate(event.value))

    def test_availability_has_no_sender_allowlist(self):
        for sender in ({"aadObjectId": USER}, {"aadObjectId": INSTANCE}, {"id": "teams-participant"}):
            self.assertTrue(is_recording_available(recording_activity(**{"from": sender})))
        for text in ("/meeting-recap", "Read another meeting's transcript"):
            self.assertFalse(is_recording_available(meeting_activity(type="message", text=text)))
        self.assertFalse(is_recording_available(recording_activity(
            conversation={"id": CHAT, "conversationType": "personal", "tenantId": TENANT},
        )))

    def test_recording_and_transcript_success_notifications(self):
        for content in ("Recording", "Transcript", "Recording+Transcript"):
            event = recording_activity(content_types=content)
            self.assertTrue(is_recording_available(event))
            parsed = RecordingAvailable.from_activity(event)
            self.assertEqual(parsed.chat_id, CHAT)
            self.assertEqual(parsed.started_at, START + timedelta(minutes=1))

    def test_notification_preserves_sharepoint_viewer_not_transcript_api_url(self):
        url = "https://contoso.sharepoint.com/:v:/g/recording?view=transcript&mode=read"
        text = recording_activity().text.replace(
            "</RecordingContent>",
            '<item type="onedriveForBusinessVideo" '
            f'uri="{url.replace("&", "&amp;")}" /></RecordingContent>',
        )
        parsed = RecordingAvailable.from_activity(recording_activity(text=text))
        self.assertEqual(parsed.viewer_url, url)

    def test_invalid_viewer_link_does_not_block_transcript_notification(self):
        for url in (
            "https://example.test/recording", "https://evilsharepoint.com/recording",
            "javascript:alert(1)", "https://teams.microsoft.com/l/chat/example/conversations",
            "https://contoso.sharepoint.com:invalid/recording",
        ):
            text = recording_activity().text.replace(
                "</RecordingContent>",
                f'<item type="onedriveForBusinessVideo" uri="{url}" /></RecordingContent>',
            )
            with self.subTest(url=url), self.assertLogs("agent.meeting_lifecycle", level="WARNING"):
                parsed = RecordingAvailable.from_activity(recording_activity(text=text))
            self.assertIsNotNone(parsed)
            self.assertIsNone(parsed.viewer_url)

    def test_nonavailability_messages_do_not_route(self):
        for event in (
            recording_activity(status="Initial"),
            recording_activity(status="ChunkFinished"),
            recording_activity(status="Failed"),
            recording_activity(content_types="Video"),
            recording_activity(type="event"),
            recording_activity(text=r'{\"scopeId\":\"synthetic\"}'),
            recording_activity(text='<URIObject type="Video.1"><RecordingStatus status="Success"/></URIObject>'),
        ):
            self.assertFalse(is_recording_available(event))

    def test_malformed_notifications_are_logged_and_ignored(self):
        text = recording_activity().text
        for malformed in (
            "<URIObject",
            '<URIObject>' + "x" * 64_000,
            '<URIObject><!ENTITY bad "value"></URIObject>',
            text.replace(f'timestamp="{(START + timedelta(minutes=1)).isoformat()}"', ""),
            text.replace((START + timedelta(minutes=1)).isoformat(), "not-a-time"),
            text.replace((START + timedelta(minutes=1)).isoformat(), "2026-10-01T14:01:00"),
        ):
            with self.assertLogs("agent.meeting_lifecycle", level="WARNING"):
                self.assertFalse(is_recording_available(recording_activity(text=malformed)))


class HandlerDispatchTests(IsolatedAsyncioTestCase):
    async def test_meeting_addition_posts_plain_text_greeting_without_model(self):
        routes = []
        app = SimpleNamespace(
            error=lambda handler: handler,
            before_turn=lambda handler: handler,
            add_route=lambda selector, handler, **kwargs: routes.append((selector, handler, kwargs)),
            auth=SimpleNamespace(exchange_token=AsyncMock(return_value=SimpleNamespace(token="synthetic"))),
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        context = SimpleNamespace(activity=meeting_added_activity(), send_activity=AsyncMock())
        selector, handler, options = next(route for route in routes if route[0](context))
        self.assertEqual(handler, handlers.on_added_to_meeting)
        self.assertEqual(options["auth_handlers"], ["AGENTIC"])
        title = "R&D <Planning> **Review**"
        graph = SimpleNamespace(get_chat_title=AsyncMock(return_value=title))
        with (
            patch.object(handlers, "processor") as processor,
            patch.object(handlers, "workiq_client") as workiq_client,
            patch("agent.app.AIProjectClient") as project,
            patch("agent.app.DefaultAzureCredential") as credential,
            self.assertLogs("agent.app", level="INFO") as logs,
        ):
            workiq_client.return_value.__aenter__ = AsyncMock(return_value=graph)
            workiq_client.return_value.__aexit__ = AsyncMock(return_value=False)
            await handler(context, None)
        self.assertIn("Agent added to a meeting chat", logs.output[0])
        processor.assert_not_called()
        project.assert_not_called()
        credential.assert_not_called()
        workiq_client.assert_called_once_with(context)
        graph.get_chat_title.assert_awaited_once_with(CHAT)
        context.send_activity.assert_awaited_once()
        greeting = context.send_activity.call_args.args[0]
        self.assertEqual(greeting.type, "message")
        self.assertEqual(greeting.text, f"Hello, thank you for adding me to {title}!")
        self.assertEqual(greeting.text_format, "plain")

    async def test_greeting_lookup_failure_does_not_invent_a_title(self):
        handlers = MeetingHandlers(SimpleNamespace(), SETTINGS)
        context = SimpleNamespace(activity=meeting_added_activity(), send_activity=AsyncMock())
        graph = SimpleNamespace(get_chat_title=AsyncMock(side_effect=WorkIQError(403, "AccessDenied")))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=graph)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(handlers, "workiq_client", return_value=manager):
            with self.assertRaises(WorkIQError):
                await handlers.on_added_to_meeting(context, None)
        context.send_activity.assert_not_awaited()

    async def test_recording_route_uses_shared_processor(self):
        routes = []
        app = SimpleNamespace(
            error=lambda handler: handler,
            before_turn=lambda handler: handler,
            add_route=lambda selector, handler, **kwargs: routes.append((selector, handler)),
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        processor = SimpleNamespace(start=AsyncMock(), end=AsyncMock(), recording_available=AsyncMock())
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=processor)
        manager.__aexit__ = AsyncMock(return_value=False)
        turn = object()
        with patch.object(handlers, "processor", return_value=manager) as shared:
            context = SimpleNamespace(activity=recording_activity())
            selected = next(handler for selector, handler in routes if selector(context))
            self.assertEqual(selected, handlers.on_recording_available)
            await selected(context, turn)
            shared.assert_called_with(context, turn)
            processor.recording_available.assert_awaited_once_with(recording_signal())
            processor.start.assert_not_awaited()
            processor.end.assert_not_awaited()

    async def test_processor_rejects_invalid_context_before_graph_or_storage(self):
        handlers = MeetingHandlers(SimpleNamespace(), SETTINGS)
        context = SimpleNamespace(activity=meeting_activity(conversation={
            "id": CHAT, "isGroup": True, "tenantId": INSTANCE,
        }))
        with patch.object(handlers, "clients") as clients:
            with self.assertRaisesRegex(ValueError, "consistent agent-user identity"):
                async with handlers.processor(context, None):
                    self.fail("Invalid identity must not reach the processor")
        clients.assert_not_called()


class LifecycleTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = MeetingState()
        self.saved = []
        self.post = AsyncMock()
        self.graph = SimpleNamespace(
            meeting_in_chat=AsyncMock(return_value={"id": "meeting-id"}),
            invited_event=AsyncMock(return_value={"id": "event-id", "body": {"content": "Approve budget"}}),
            list_transcripts=AsyncMock(return_value={"items": [], "has_more": False}),
            get_transcript=AsyncMock(return_value={"content": "00:10 Budget approved."}),
        )
        self.analysis = SimpleNamespace(
            extract_agenda=AsyncMock(return_value=["Approve budget"]),
            compare=AsyncMock(return_value="**Agenda closure - agent-generated**\nClosed: Approve budget"),
        )

        async def save():
            self.saved.append(self.state.model_dump(mode="json"))

        self.processor = MeetingLifecycle(
            self.state, self.graph, self.analysis, save, self.post,
        )

    def ready_transcript(self):
        self.graph.list_transcripts.return_value = {
            "items": [{
                "id": "transcript", "createdDateTime": (START + timedelta(minutes=1)).isoformat(),
                "endDateTime": END.isoformat(),
            }],
            "has_more": False,
        }

    async def test_start_posts_snapshot_once_and_survives_reload(self):
        await self.processor.start(*meeting_args())
        self.assertEqual(self.post.await_count, 1)
        self.assertIn("Agenda reminder", self.post.call_args.args[0])
        self.assertEqual(next(iter(self.saved[-2]["occurrences"].values()))["reminder"], "reserved")
        self.processor.state = MeetingState.model_validate(self.saved[-1])
        await self.processor.start(*meeting_args())
        self.assertEqual(self.post.await_count, 1)
        self.graph.invited_event.assert_awaited_once_with(JOIN, START)

    async def test_sdk_models_are_unchanged_while_state_is_normalized(self):
        start, chat_id = meeting_args(
            when=START.astimezone(timezone(timedelta(hours=2))), join_url=f" {JOIN} ",
        )
        end, _ = meeting_args(
            "end", when=END.astimezone(timezone(timedelta(hours=-4))), join_url=f" {JOIN} ",
        )
        original_start, original_end = start.model_dump(), end.model_dump()
        await self.processor.start(start, chat_id)
        await self.processor.start(*meeting_args())
        self.assertEqual(len(self.state.occurrences), 1)
        self.graph.invited_event.assert_awaited_once_with(JOIN, START)
        await self.processor.end(end, chat_id)
        record = next(iter(self.state.occurrences.values()))
        self.assertEqual(record.chat_id, CHAT)
        self.assertEqual(record.join_url, JOIN)
        self.assertEqual(record.started_at, START)
        self.assertIs(record.started_at.tzinfo, timezone.utc)
        self.assertEqual(record.ended_at, END)
        self.assertIs(record.ended_at.tzinfo, timezone.utc)
        self.assertEqual(start.model_dump(), original_start)
        self.assertEqual(end.model_dump(), original_end)

    async def test_end_cannot_use_another_chat_id(self):
        await self.processor.start(*meeting_args())
        with self.assertRaisesRegex(ValueError, "recorded start"):
            await self.processor.end(*meeting_args("end", chat_id="another-chat"))
        self.assertIsNone(next(iter(self.state.occurrences.values())).ended_at)
        self.graph.list_transcripts.assert_not_awaited()

    async def test_no_agenda_posts_nothing(self):
        self.analysis.extract_agenda.return_value = []
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        self.post.assert_not_awaited()
        self.graph.list_transcripts.assert_not_awaited()

    async def test_chat_binding_failure_never_posts(self):
        self.graph.meeting_in_chat.side_effect = ValueError("wrong chat")
        with self.assertRaises(ValueError):
            await self.processor.start(*meeting_args())
        self.post.assert_not_awaited()
        self.analysis.extract_agenda.assert_not_awaited()

    async def test_end_without_start_never_invents_agenda(self):
        with self.assertRaisesRegex(ValueError, "recorded start"):
            await self.processor.end(*meeting_args("end"))
        self.post.assert_not_awaited()

    async def test_end_acknowledges_before_transcript_fetch_fails(self):
        await self.processor.start(*meeting_args())

        async def unavailable(_meeting_id):
            record = next(iter(self.processor.state.occurrences.values()))
            self.assertEqual(record.ended_at, END)
            self.assertEqual(record.pending_notice, "sent")
            self.assertIn("prepare meeting notes", self.post.call_args.args[0])
            self.assertEqual(
                next(iter(self.saved[-1]["occurrences"].values()))["pending_notice"], "sent",
            )
            raise WorkIQError(403, "AccessDenied")

        self.graph.list_transcripts.side_effect = unavailable
        with self.assertRaises(WorkIQError):
            await self.processor.end(*meeting_args("end"))
        self.assertEqual(self.post.await_count, 2)
        self.analysis.compare.assert_not_awaited()
        self.processor.state = MeetingState.model_validate(self.saved[-1])
        await self.processor.end(*meeting_args("end"))
        self.assertEqual(self.post.await_count, 2)

    async def test_end_with_ready_transcript_acknowledges_then_reports(self):
        await self.processor.start(*meeting_args())
        self.ready_transcript()
        await self.processor.end(*meeting_args("end"))
        messages = [call.args[0] for call in self.post.call_args_list]
        self.assertEqual(len(messages), 3)
        self.assertIn("prepare meeting notes", messages[1])
        self.assertIn("Agenda closure", messages[2])
        self.assertEqual(
            self.analysis.compare.call_args.kwargs["source_url"],
            "https://teams.microsoft.com/l/chat/19%3Ameeting%40thread.v2/conversations",
        )
        self.assertIn("Select Recap", messages[2])

    async def test_availability_viewer_link_is_persisted_and_used_for_citations(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        self.ready_transcript()
        url = "https://contoso.sharepoint.com/:v:/g/personal/organizer/recording"
        await self.processor.recording_available(
            RecordingAvailable(chat_id=CHAT, started_at=START + timedelta(minutes=1), viewer_url=url),
        )
        self.assertEqual(self.analysis.compare.call_args.kwargs["source_url"], url)
        self.assertIn("recording/transcript viewer", self.post.call_args.args[0])
        restored = MeetingState.model_validate(self.saved[-1])
        self.assertEqual(next(iter(restored.occurrences.values())).viewer_url, url)

    async def test_multiple_transcript_segments_link_to_recap_not_one_recording(self):
        await self.processor.start(*meeting_args())
        self.ready_transcript()
        self.graph.list_transcripts.return_value["items"].append({
            **self.graph.list_transcripts.return_value["items"][0], "id": "second-transcript",
        })
        record = next(iter(self.state.occurrences.values()))
        record.viewer_url = "https://contoso.sharepoint.com/:v:/g/one-recording"
        await self.processor.end(*meeting_args("end"))
        self.assertIn("/l/chat/", self.analysis.compare.call_args.kwargs["source_url"])
        self.assertIn("Select Recap", self.post.call_args.args[0])

    async def test_delayed_transcript_is_processed_on_availability(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        self.assertIn("retry automatically", self.post.call_args.args[0])
        self.analysis.compare.assert_not_awaited()
        await self.processor.end(*meeting_args("end"))
        self.assertEqual(self.post.await_count, 2)
        self.ready_transcript()
        await self.processor.recording_available(recording_signal())
        self.assertEqual(self.post.await_count, 3)
        self.assertNotIn("Existing Copilot summary", self.post.call_args.args[0])
        await self.processor.recording_available(recording_signal())
        self.assertEqual(self.post.await_count, 3)

    async def test_report_uses_only_transcripts_without_reading_copilot_summaries(self):
        await self.processor.start(*meeting_args())
        self.ready_transcript()
        self.graph.list_meeting_insights = AsyncMock(side_effect=AssertionError("Must not read insights"))
        self.graph.get_meeting_insight = AsyncMock(side_effect=AssertionError("Must not read insights"))
        await self.processor.end(*meeting_args("end"))
        self.graph.list_meeting_insights.assert_not_awaited()
        self.graph.get_meeting_insight.assert_not_awaited()
        self.assertNotIn("Copilot summary", self.post.call_args.args[0])
        self.assertEqual(self.analysis.compare.call_args.args[1], {"transcript:transcript": "00:10 Budget approved."})

    async def test_previous_occurrence_transcript_is_not_used(self):
        await self.processor.start(*meeting_args())
        self.graph.list_transcripts.return_value = {
            "items": [{"id": "old", "createdDateTime": (START - timedelta(days=7)).isoformat()}],
            "has_more": False,
        }
        await self.processor.end(*meeting_args("end"))
        self.graph.get_transcript.assert_not_awaited()
        self.analysis.compare.assert_not_awaited()

    async def test_missing_timestamps_and_pagination_fail_closed(self):
        await self.processor.start(*meeting_args())
        self.graph.list_transcripts.return_value = {"items": [{"id": "unknown"}], "has_more": False}
        with self.assertRaisesRegex(ValueError, "timestamps"):
            await self.processor.end(*meeting_args("end"))
        self.graph.list_transcripts.return_value = {"items": [], "has_more": True}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            await self.processor.recording_available(recording_signal())
        self.analysis.compare.assert_not_awaited()

    async def test_recurrence_uses_distinct_agenda_snapshots(self):
        await self.processor.start(*meeting_args())
        self.ready_transcript()
        await self.processor.end(*meeting_args("end"))
        self.analysis.extract_agenda.return_value = ["Approve launch"]
        await self.processor.start(*meeting_args(when=START + timedelta(days=7)))
        self.assertEqual(len(self.state.occurrences), 2)
        self.assertIn("Approve launch", self.post.call_args.args[0])
        count = self.post.await_count
        await self.processor.end(*meeting_args("end"))  # Old end cannot end the new occurrence.
        self.assertEqual(self.post.await_count, count)
        self.assertIsNone(list(self.state.occurrences.values())[-1].ended_at)

    async def test_rejoining_same_meeting_with_new_start_posts_new_reminder(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        await self.processor.start(*meeting_args(when=END + timedelta(minutes=1)))
        records = list(self.state.occurrences.values())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].ended_at, END)
        self.assertIsNone(records[1].ended_at)
        self.assertEqual(records[1].reminder, "sent")
        self.assertIn("Agenda reminder", self.post.call_args.args[0])

    async def test_ambiguous_delivery_not_blindly_reposted(self):
        self.post.side_effect = TimeoutError("unknown delivery outcome")
        with self.assertRaises(TimeoutError):
            await self.processor.start(*meeting_args())
        self.assertEqual(next(iter(self.saved[-1]["occurrences"].values()))["reminder"], "reserved")
        await self.processor.start(*meeting_args())
        self.assertEqual(self.post.await_count, 1)

    async def test_notification_cannot_target_different_chat(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        count = self.graph.list_transcripts.await_count
        with self.assertLogs("agent.meeting_lifecycle", level="INFO"):
            await self.processor.recording_available(recording_signal(chat_id="another-chat"))
        self.assertEqual(self.graph.list_transcripts.await_count, count)
        self.assertFalse(next(iter(self.state.occurrences.values())).artifacts_available)

    async def test_notification_before_end_waits_and_survives_reload(self):
        await self.processor.start(*meeting_args())
        await self.processor.recording_available(recording_signal())
        self.graph.list_transcripts.assert_not_awaited()
        self.analysis.compare.assert_not_awaited()
        self.processor.state = MeetingState.model_validate(self.saved[-1])
        self.ready_transcript()
        await self.processor.end(*meeting_args("end"))
        self.analysis.compare.assert_awaited_once()
        self.assertEqual(self.post.await_count, 3)

    async def test_notification_targets_its_occurrence_not_latest_in_chat(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        await self.processor.start(*meeting_args(when=START + timedelta(days=7)))
        await self.processor.end(*meeting_args("end", when=END + timedelta(days=7)))
        self.ready_transcript()
        await self.processor.recording_available(recording_signal())
        records = list(self.state.occurrences.values())
        self.assertEqual(records[0].recap, "sent")
        self.assertEqual(records[1].recap, "unsent")
        self.assertFalse(records[1].artifacts_available)

    async def test_notification_without_observed_occurrence_is_logged_and_ignored(self):
        with self.assertLogs("agent.meeting_lifecycle", level="INFO"):
            await self.processor.recording_available(recording_signal())
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        count = self.graph.list_transcripts.await_count
        for when in (START - timedelta(days=7), END + timedelta(minutes=1)):
            with self.assertLogs("agent.meeting_lifecycle", level="INFO"):
                await self.processor.recording_available(recording_signal(when=when))
        self.assertEqual(self.graph.list_transcripts.await_count, count)

    async def test_graph_lag_after_success_retries_without_user_action(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        self.ready_transcript()
        ready = self.graph.list_transcripts.return_value
        request_id = "11111111-2222-3333-4444-555555555555"
        self.graph.list_transcripts.side_effect = [
            WorkIQError(
                404, "NotFound", request_id=request_id,
                diagnostics=WorkIQDiagnostics("fetch", "upstream_error", rpc_code=-32000),
            ), {"items": [], "has_more": False}, ready,
        ]
        with (
            patch("agent.meeting_lifecycle.asyncio.sleep", new_callable=AsyncMock) as sleep,
            self.assertLogs("agent.meeting_lifecycle", level="WARNING") as logs,
        ):
            await self.processor.recording_available(recording_signal())
        self.assertIn(request_id, "\n".join(logs.output))
        self.assertIn("-32000", "\n".join(logs.output))
        self.assertEqual(sleep.await_count, 2)
        self.analysis.compare.assert_awaited_once()
        self.assertEqual(self.post.await_count, 3)

    async def test_graph_lag_retries_are_bounded_and_pending_state_retained(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        with (
            patch("agent.meeting_lifecycle.asyncio.sleep", new_callable=AsyncMock) as sleep,
            self.assertLogs("agent.meeting_lifecycle", level="WARNING") as logs,
        ):
            await self.processor.recording_available(recording_signal())
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(self.graph.list_transcripts.await_count, 4)
        self.assertIn("still pending", logs.output[-1])
        self.assertEqual(next(iter(self.state.occurrences.values())).recap, "unsent")
        self.ready_transcript()
        await self.processor.recording_available(recording_signal())
        self.analysis.compare.assert_awaited_once()

    async def test_permission_failure_is_not_retried_or_hidden(self):
        await self.processor.start(*meeting_args())
        await self.processor.end(*meeting_args("end"))
        self.graph.list_transcripts.side_effect = WorkIQError(403, "AccessDenied")
        with patch("agent.meeting_lifecycle.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(WorkIQError):
                await self.processor.recording_available(recording_signal())
        sleep.assert_not_awaited()

    async def test_oversized_transcript_not_summarized_as_complete(self):
        await self.processor.start(*meeting_args())
        self.ready_transcript()
        self.graph.get_transcript.return_value = {"content": "x" * 120001}
        with self.assertRaisesRegex(ValueError, "complete-analysis limit"):
            await self.processor.end(*meeting_args("end"))
        self.analysis.compare.assert_not_awaited()


class SdkPersistenceTests(IsolatedAsyncioTestCase):
    async def test_business_state_checkpoints_prevent_replay(self):
        from test_sdk_dispatch import replay

        adapter = replay.OfflineAdapter()
        app = AgentApplication(
            storage=MemoryStorage(), adapter=adapter,
            connection_manager=replay.OfflineConnections(), start_typing_timer=False,
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)

        @app.error
        async def fail_on_error(context, error):
            raise error

        post = AsyncMock()

        async def send_activities(context, activities):
            for message in activities:
                await post(message.text)
            return [ResourceResponse(id="synthetic") for _ in activities]

        adapter.send_activities = AsyncMock(side_effect=send_activities)
        graph = SimpleNamespace(
            meeting_in_chat=AsyncMock(return_value={"id": "meeting"}),
            invited_event=AsyncMock(return_value={"id": "event", "body": {"content": "Approve budget"}}),
            list_transcripts=AsyncMock(side_effect=[
                {"items": [], "has_more": False},
                {"items": [{
                    "id": "transcript", "createdDateTime": START.isoformat(), "endDateTime": END.isoformat(),
                }], "has_more": False},
            ]),
            get_transcript=AsyncMock(return_value={"content": "Budget approved."}),
        )
        analysis = SimpleNamespace(
            extract_agenda=AsyncMock(return_value=["Approve budget"]),
            compare=AsyncMock(return_value="Closed: Approve budget"),
        )
        project = MagicMock()
        project.__aenter__ = AsyncMock(return_value=project)
        project.__aexit__ = AsyncMock()
        project.get_openai_client.return_value = AsyncMock()
        credential = AsyncMock()
        with (
            patch("agent.app.AIProjectClient", return_value=project),
            patch("agent.app.DefaultAzureCredential", return_value=credential),
            patch.object(handlers, "workiq_client") as workiq_client,
            patch("agent.app.MeetingAnalysis", return_value=analysis),
            patch.object(app.auth, "_start_or_continue_sign_in", new_callable=AsyncMock) as sign_in,
        ):
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: True)
            workiq_client.return_value.__aenter__ = AsyncMock(return_value=graph)
            workiq_client.return_value.__aexit__ = AsyncMock(return_value=False)
            for event in (
                meeting_activity(), meeting_activity(),
                meeting_activity("end"), meeting_activity("end"),
                recording_activity(),
                recording_activity(),
            ):
                event.from_property.id = f"8:orgid:{USER}"
                event.recipient.id = f"8:orgid:{AGENT_USER}"
                event.service_url = "https://example.test/teams"
                await adapter.run_pipeline(TurnContext(adapter, event), app.on_turn)
        self.assertEqual(post.await_count, 3)
        self.assertIn("Agenda reminder", post.call_args_list[0].args[0])
        self.assertIn("prepare meeting notes", post.call_args_list[1].args[0])
        self.assertIn("Closed: Approve budget", post.call_args_list[2].args[0])
        self.assertEqual(graph.list_transcripts.await_count, 2)
        analysis.compare.assert_awaited_once()
        self.assertEqual(graph.invited_event.await_count, 1)
        self.assertEqual(workiq_client.call_count, 6)
