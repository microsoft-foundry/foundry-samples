"""Offline end-to-end SDK dispatch of the unchanged sanitized captured events."""

from copy import deepcopy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from microsoft_agents.activity import Activity
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage, TurnContext
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue

from agent.app import MeetingHandlers, register_handlers
from test_meeting_assistant import SETTINGS


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay-sdk-payloads.py"
SPEC = importlib.util.spec_from_file_location("replay_sdk_payloads", SCRIPT)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def fixture(kind):
    return json.loads(
        (replay.FIXTURE_DIR / f"meeting-{kind}.json").read_text(encoding="utf-8")
    )


class SDKDispatchTests(IsolatedAsyncioTestCase):
    async def test_incomplete_authorization_prevents_lifecycle_callback(self):
        adapter = replay.OfflineAdapter()
        app = AgentApplication(
            storage=MemoryStorage(), adapter=adapter,
            connection_manager=replay.OfflineConnections(), start_typing_timer=False,
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        with (
            patch.object(handlers, "processor") as processor,
            patch.object(app.auth, "_start_or_continue_sign_in", new_callable=AsyncMock) as sign_in,
        ):
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: False)
            for kind in ("start", "end"):
                event = Activity.model_validate(fixture(kind))
                await adapter.run_pipeline(TurnContext(adapter, event), app.on_turn)
            processor.assert_not_called()
            self.assertEqual(sign_in.await_count, 2)

    async def test_application_routes_accept_captured_events_without_rewriting_values(self):
        adapter = replay.OfflineAdapter()
        app = AgentApplication(
            storage=MemoryStorage(), adapter=adapter,
            connection_manager=replay.OfflineConnections(), start_typing_timer=False,
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        processor = SimpleNamespace(start=AsyncMock(), end=AsyncMock())
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=processor)
        manager.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(handlers, "processor", return_value=manager),
            patch.object(app.auth, "_start_or_continue_sign_in", new_callable=AsyncMock) as sign_in,
        ):
            # Only authorization and downstream business APIs are offline doubles.
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: True)
            for kind in ("start", "end"):
                payload = fixture(kind)
                original = deepcopy(payload)
                event = Activity.model_validate(payload)
                await adapter.run_pipeline(TurnContext(adapter, event), app.on_turn)
                method = processor.start if kind == "start" else processor.end
                method.assert_awaited_once()
                meeting, chat_id = method.call_args.args
                model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
                self.assertIsInstance(meeting, model)
                self.assertEqual(meeting.join_url, payload["value"]["JoinUrl"])
                self.assertEqual(chat_id, payload["conversation"]["id"])
                timestamp = meeting.start_time if kind == "start" else meeting.end_time
                self.assertEqual(
                    timestamp.isoformat(),
                    datetime.fromisoformat(
                        payload["value"]["StartTime" if kind == "start" else "EndTime"]
                    ).isoformat(),
                )
                self.assertEqual(event.value, original["value"])
                self.assertEqual(payload, original)
            self.assertEqual(sign_in.await_count, 2)
            self.assertTrue(all(call.args[2] == "AGENTIC" for call in sign_in.call_args_list))

    async def test_handlers_forward_the_same_sdk_meeting_objects(self):
        handlers = MeetingHandlers(SimpleNamespace(), SETTINGS)
        processor = SimpleNamespace(start=AsyncMock(), end=AsyncMock())
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=processor)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(handlers, "processor", return_value=manager):
            for kind in ("start", "end"):
                payload = fixture(kind)
                model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
                meeting = model.model_validate(payload["value"])
                original = meeting.model_dump()
                context = SimpleNamespace(activity=Activity.model_validate(payload))
                handler = handlers.on_meeting_start if kind == "start" else handlers.on_meeting_end
                await handler(context, None, meeting)
                method = processor.start if kind == "start" else processor.end
                method.assert_awaited_once_with(meeting, payload["conversation"]["id"])
                self.assertIs(method.call_args.args[0], meeting)
                self.assertEqual(meeting.model_dump(), original)

    async def test_native_routes_reject_unsafe_events_before_business_processing(self):
        adapter = replay.OfflineAdapter()
        app = AgentApplication(
            storage=MemoryStorage(), adapter=adapter,
            connection_manager=replay.OfflineConnections(), start_typing_timer=False,
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        with (
            patch.object(handlers, "processor") as processor,
            patch.object(app.auth, "_start_or_continue_sign_in", new_callable=AsyncMock) as sign_in,
        ):
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: True)
            for kind in ("start", "end"):
                timestamp = "StartTime" if kind == "start" else "EndTime"
                for changes in (
                    {"Title": " "},
                    {"Id": ""},
                    {"MeetingType": "Channel"},
                    {"JoinUrl": ""},
                    {timestamp: "2026-10-02T20:48:16"},
                    {timestamp: None},
                ):
                    with self.subTest(kind=kind, fields=list(changes)):
                        payload = fixture(kind)
                        payload["value"].update(changes)
                        original = deepcopy(payload)
                        event = Activity.model_validate(payload)
                        with self.assertLogs("agent.app", level="ERROR"):
                            await adapter.run_pipeline(TurnContext(adapter, event), app.on_turn)
                        processor.assert_not_called()
                        self.assertEqual(event.value, original["value"])
                        self.assertEqual(payload, original)

    async def test_sdk_routes_ignore_non_meeting_events(self):
        adapter = replay.OfflineAdapter()
        app = AgentApplication(
            storage=MemoryStorage(), adapter=adapter,
            connection_manager=replay.OfflineConnections(), start_typing_timer=False,
        )
        handlers = MeetingHandlers(app, SETTINGS)
        register_handlers(app, handlers)
        with (
            patch.object(handlers, "processor") as processor,
            patch.object(app.auth, "_start_or_continue_sign_in", new_callable=AsyncMock) as sign_in,
        ):
            for changes in (
                {"name": "calendar.event.start"},
                {"type": "message"},
            ):
                payload = fixture("start")
                payload.update(changes)
                event = Activity.model_validate(payload)
                await adapter.run_pipeline(TurnContext(adapter, event), app.on_turn)
            processor.assert_not_called()
            sign_in.assert_not_awaited()

    async def test_captured_start_and_end_succeed_in_actual_sdk_dispatch(self):
        for kind in ("start", "end"):
            with self.subTest(kind=kind):
                payload = fixture(kind)
                original = deepcopy(payload)
                result = await replay.replay_payload(payload)
                self.assertTrue(result["dispatch_succeeded"], result)
                self.assertEqual(result["stage"], "sdk_meeting_callback")
                self.assertTrue(result["sdk_before_turn_entered"])
                self.assertTrue(result["sdk_before_turn_completed"])
                self.assertTrue(result["callback_reached"])
                self.assertIsNone(result["error"])
                self.assertEqual(
                    result["meeting_model"],
                    "MeetingStartEventValue" if kind == "start" else "MeetingEndEventValue",
                )
                self.assertTrue(result["common_fields_match"])
                self.assertTrue(result["timestamp_matches"])
                self.assertTrue(result["activity_value_unchanged"])
                self.assertTrue(result["input_payload_unchanged"])
                self.assertEqual(payload, original)
                self.assertEqual(result["channel_data_types"]["before"], "dict")
                self.assertEqual(result["channel_data_types"]["after"], "ChannelData")
                self.assertEqual(result["activity_class_after"], "TeamsActivity")
                serialized = json.dumps(result)
                for private_value in (
                    payload["value"]["Id"], payload["value"]["Title"],
                    payload["value"]["JoinUrl"], payload["serviceUrl"],
                    payload["recipient"]["agenticUserId"],
                ):
                    self.assertNotIn(private_value, serialized)

    async def test_missing_timestamp_fails_in_native_sdk_dispatch(self):
        for kind in ("start", "end"):
            payload = fixture(kind)
            timestamp = "StartTime" if kind == "start" else "EndTime"
            payload["value"].pop(timestamp)
            result = await replay.replay_payload(payload)
            self.assertFalse(result["dispatch_succeeded"])
            self.assertFalse(result["callback_reached"])
            self.assertEqual(result["stage"], "sdk_meeting_dispatch")
            self.assertEqual(result["error"]["missing_fields"], [[timestamp]])
            self.assertTrue(result["activity_value_unchanged"])
            self.assertTrue(result["input_payload_unchanged"])

    async def test_earlier_sdk_failure_is_reported_without_bypass(self):
        payload = fixture("start")
        # Deliberately malformed negative case, not a captured-payload fixture.
        payload["channelData"]["tenant"] = 42
        original = deepcopy(payload)
        result = await replay.replay_payload(payload)
        self.assertFalse(result["dispatch_succeeded"])
        self.assertEqual(result["stage"], "sdk_before_turn")
        self.assertTrue(result["sdk_before_turn_entered"])
        self.assertFalse(result["sdk_before_turn_completed"])
        self.assertFalse(result["callback_reached"])
        self.assertEqual(result["error"]["model"], "ChannelData")
        self.assertEqual(result["error"]["fields"][0]["loc"], ["tenant"])
        self.assertTrue(result["activity_value_unchanged"])
        self.assertEqual(payload, original)

    async def test_transport_and_token_seams_fail_closed(self):
        adapter = replay.OfflineAdapter()
        from microsoft_agents.activity import Activity
        from microsoft_agents.hosting.core import TurnContext

        context = TurnContext(adapter, Activity.model_validate(fixture("start")))
        with self.assertRaisesRegex(RuntimeError, "outbound send"):
            await adapter.send_activities(context, [])
        with self.assertRaisesRegex(RuntimeError, "token acquisition"):
            replay.OfflineConnections().get_token_provider(None, "")


class ActivityEventModelTests(TestCase):
    def test_native_models_preserve_pascal_case_fields_and_timestamps(self):
        for kind, model, wire_field, model_field in (
            ("start", MeetingStartEventValue, "StartTime", "start_time"),
            ("end", MeetingEndEventValue, "EndTime", "end_time"),
        ):
            with self.subTest(kind=kind):
                payload = fixture(kind)["value"]
                original = deepcopy(payload)
                self.assertIn(wire_field, payload)
                parsed = model.model_validate(payload)
                self.assertEqual(
                    getattr(parsed, model_field), datetime.fromisoformat(payload[wire_field]),
                )
                self.assertEqual(parsed.id, payload["Id"])
                self.assertEqual(parsed.meeting_type, payload["MeetingType"])
                self.assertEqual(parsed.join_url, payload["JoinUrl"])
                self.assertEqual(parsed.title, payload["Title"])
                self.assertEqual(payload, original)
