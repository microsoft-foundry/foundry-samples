from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from microsoft_agents.hosting.core import ConnectorClientBase

from foundry_m365_autopilot.activity_context import build_activity_context_attachment
from foundry_m365_autopilot.activity_filter import (
    ActivityDeduplicator,
    is_agent_authored_activity,
)
from foundry_m365_autopilot.capabilities import build_capabilities_attachment
from foundry_m365_autopilot.meeting_delegate_cards import (
    ADD_RULE_VERB,
    REMOVE_RULE_VERB,
    SAVE_RULES_VERB,
    SUBMIT_DISPLAY_TEXTS,
    SUBMIT_TEXT,
    build_meeting_delegate_attachment,
    extract_configuration_meeting_id,
    get_submit_action,
    is_submit_message,
    rebuild_form_data,
)
from foundry_m365_autopilot.agent import (
    CALENDAR_MCP_SERVERS,
    MEETING_MCP_SERVERS,
    OUT_OF_SCOPE_REPLY,
    FoundryDigitalWorkerAgent,
    _is_meeting_list_command,
)
from foundry_m365_autopilot.host_agent_server import _update_or_send_card
from foundry_m365_autopilot.meeting_store import (
    LocalFileMeetingDelegateStore,
    build_delegate,
    describe_meeting_activity,
    extract_meeting_id,
    message_mentions_agent,
)
from foundry_m365_autopilot.upcoming_meetings import (
    build_upcoming_meetings_attachment,
)


class _FakeAuth:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    async def exchange_token(self, context, *, scopes, auth_handler_id):
        self.scopes = scopes
        return SimpleNamespace(token="graph-token")


class _ManagerResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "id": "agent-user-id",
            "userPrincipalName": "meeting-agent@contoso.com",
            "manager": {
                "id": "manager-object-id",
                "displayName": "Manager One",
                "userPrincipalName": "manager@contoso.com",
                "mail": "manager@contoso.com",
            },
        }


class _ManagerHttpClient:
    async def get(self, url, *, params, headers):
        self.url = url
        self.params = params
        self.headers = headers
        return _ManagerResponse()


class _OnlineMeetingResponse:
    status_code = 200
    text = ""

    def __init__(self, join_web_url: str) -> None:
        self.join_web_url = join_web_url

    def json(self):
        return {
            "value": [
                {
                    "id": "online-meeting-id",
                    "joinWebUrl": self.join_web_url,
                    "chatInfo": {"threadId": "meeting-thread-id"},
                }
            ]
        }


class _OnlineMeetingHttpClient(_ManagerHttpClient):
    def __init__(self, join_web_url: str) -> None:
        self.join_web_url = join_web_url
        self.online_meeting_params = None

    async def get(self, url, *, params, headers):
        if url.endswith("/me/onlineMeetings"):
            self.online_meeting_params = params
            return _OnlineMeetingResponse(self.join_web_url)
        return await super().get(url, params=params, headers=headers)


class _IntentResponse:
    def __init__(
        self,
        output_text: str = "",
        status_code: int = 200,
        response_json: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self._output_text = output_text
        self._response_json = response_json
        self.text = output_text

    def json(self):
        if self._response_json is not None:
            return self._response_json
        return {"output_text": self._output_text}


class _IntentHttpClient:
    def __init__(self, response: _IntentResponse) -> None:
        self.response = response
        self.requests: list[dict] = []

    async def get(self, url, *, params, headers):
        return _ManagerResponse()

    async def post(self, url, *, json, headers):
        self.requests.append({"url": url, "json": json, "headers": headers})
        return self.response


class _CalendarEventResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "location": {"displayName": "Microsoft Teams Meeting"},
            "onlineMeeting": {
                "joinUrl": "https://teams.microsoft.com/l/meetup-join/authoritative"
            },
            "webLink": "https://outlook.office.com/calendar/item/event",
        }


class _CalendarEventHttpClient(_IntentHttpClient):
    def __init__(self, response: _IntentResponse) -> None:
        super().__init__(response)
        self.event_requests: list[dict] = []

    async def get(self, url, *, params, headers):
        if "/me/events/" in url:
            self.event_requests.append(
                {"url": url, "params": params, "headers": headers}
            )
            return _CalendarEventResponse()
        return await super().get(url, params=params, headers=headers)


class _UnavailableCalendarEventHttpClient(_IntentHttpClient):
    async def get(self, url, *, params, headers):
        if "/me/events/" in url:
            return _IntentResponse(status_code=503)
        return await super().get(url, params=params, headers=headers)


class _FakeServices:
    def __init__(self, values: dict | None = None) -> None:
        self._values = values or {}

    def get(self, key):
        return self._values.get(key)


class _FakeTeamsConnector:
    async def fetch_meeting_info(self, meeting_id: str):
        self.meeting_id = meeting_id
        return SimpleNamespace(
            details=SimpleNamespace(
                ms_graph_resource_id="AAMk-calendar-event-id",
                scheduled_start_time="2026-09-15T15:18:00Z",
                scheduled_end_time="2026-09-15T15:19:00Z",
            )
        )


class MeetingAssistantTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "AzureOpenAIResponsesEndpoint": "https://example.test/openai/v1/responses",
                "ModelDeployment": "test-model",
                "AZURE_OPENAI_API_KEY": "test-key",
            },
            clear=False,
        )
        self.environment.start()
        self.agent = FoundryDigitalWorkerAgent()
        self.agent._http_client = _ManagerHttpClient()
        self.agent._manager_cache = {}

    def tearDown(self) -> None:
        self.environment.stop()

    def _manager_context(self):
        return SimpleNamespace(
            activity=SimpleNamespace(
                id="manager-turn-id",
                channel_id="msteams",
                text="",
                from_property=SimpleNamespace(
                    name="Manager One",
                    id="manager-object-id",
                    aad_object_id="manager-object-id",
                ),
                conversation=SimpleNamespace(id="manager-conversation-id"),
                recipient=SimpleNamespace(
                    id="agent-recipient-id",
                    name="Meeting Agent",
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                    agentic_app_id="agent-app-id",
                ),
            )
        )

    def _participant_context(self, *, message_id="message-id"):
        return SimpleNamespace(
            activity=SimpleNamespace(
                id=message_id,
                channel_id="msteams",
                channel_data={"meetingId": "meeting-1"},
                from_property=SimpleNamespace(
                    name="Alice",
                    id="alice-object-id",
                    aad_object_id="alice-object-id",
                ),
                conversation=SimpleNamespace(id="meeting-chat-id"),
                recipient=SimpleNamespace(
                    id="agent-recipient-id",
                    name="Meeting Agent",
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                    agentic_app_id="agent-app-id",
                ),
            )
        )

    def test_manifest_contains_only_meeting_servers(self) -> None:
        labels = tuple(server["mcpServerName"] for server in self.agent._mcp_servers)
        self.assertEqual(labels, MEETING_MCP_SERVERS)

    def test_filters_agent_authored_activity(self) -> None:
        activity = self._participant_context().activity
        activity.from_property.id = activity.recipient.id

        self.assertTrue(is_agent_authored_activity(activity))

    def test_does_not_filter_user_authored_activity(self) -> None:
        activity = self._participant_context().activity

        self.assertFalse(is_agent_authored_activity(activity))

    def test_deduplicates_retried_activity_id(self) -> None:
        activity = self._participant_context(message_id="replayed-activity-id").activity
        deduplicator = ActivityDeduplicator()

        self.assertFalse(deduplicator.is_duplicate(activity))
        self.assertTrue(deduplicator.is_duplicate(activity))

    def test_activity_without_id_is_not_deduplicated(self) -> None:
        activity = self._participant_context(message_id="").activity
        deduplicator = ActivityDeduplicator()

        self.assertFalse(deduplicator.is_duplicate(activity))
        self.assertFalse(deduplicator.is_duplicate(activity))

    async def test_build_tools_returns_only_meeting_mcp_descriptors(self) -> None:
        auth = SimpleNamespace(
            exchange_token=AsyncMock(return_value=SimpleNamespace(token="token"))
        )
        tools = await self.agent._build_mcp_tools(
            auth,
            "AGENTIC",
            SimpleNamespace(),
            allowed_labels=MEETING_MCP_SERVERS,
        )

        self.assertEqual(len(tools), 2)
        self.assertEqual(
            {tool["server_label"] for tool in tools}, set(MEETING_MCP_SERVERS)
        )
        self.assertFalse(any(tool["server_label"] == "mcp_MailTools" for tool in tools))

    def test_builds_activity_context_card_with_manager_section(self) -> None:
        attachment = build_activity_context_attachment(
            self._manager_context().activity,
            "session-id-meeting-1234567890",
            manager={
                "displayName": "Manager One",
                "userPrincipalName": "manager@contoso.com",
                "mail": "manager@contoso.com",
            },
        )
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertIn("Agent Manager", serialized)
        self.assertIn("Only this Manager can configure", serialized)
        self.assertIn("manager@contoso.com", serialized)
        self.assertIn("session-id-meeting-1234567890", serialized)
        sections = attachment["content"]["body"][2:]
        self.assertTrue(all(section["style"] == "emphasis" for section in sections))
        self.assertTrue(all(section["separator"] is True for section in sections))

    def test_builds_fixed_meeting_capabilities_card(self) -> None:
        attachment = build_capabilities_attachment()
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertNotIn("Manager-controlled delegation", serialized)
        self.assertIn("Delegated meeting lookup", serialized)
        self.assertIn("Agent has been added to attend on behalf", serialized)
        self.assertNotIn("Meetings with your Manager", serialized)
        self.assertIn("Meeting-chat responses", serialized)
        self.assertNotIn("Out-of-scope questions", serialized)
        self.assertNotIn("Follow-up reporting", serialized)

    async def test_model_classifies_capabilities_without_tools(self) -> None:
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse("CAPABILITIES")
        )

        intent = await self.agent.classify_user_intent(
            "你好，请介绍一下你能做什么"
        )

        self.assertEqual(intent, self.agent.CAPABILITIES_INTENT)
        request = self.agent._http_client.requests[0]["json"]
        self.assertNotIn("tools", request)
        self.assertEqual(request["input"], "你好，请介绍一下你能做什么")

    async def test_model_classification_failure_defaults_to_other(self) -> None:
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse(status_code=500)
        )

        intent = await self.agent.classify_user_intent("Schedule a meeting")

        self.assertEqual(intent, self.agent.OTHER_INTENT)

    async def test_model_classifies_upcoming_meeting_query(self) -> None:
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse("LIST_MEETINGS")
        )

        intent = await self.agent.classify_user_intent("列出我还没开始的会议")

        self.assertEqual(intent, self.agent.LIST_MEETINGS_INTENT)

    async def test_meeting_management_requests_are_unsupported(self) -> None:
        for message in (
            "Create a meeting tomorrow",
            "Show meeting details",
            "Update meeting event-id",
            "Delete meeting event-id",
        ):
            with self.subTest(message=message):
                self.agent._http_client = _IntentHttpClient(
                    _IntentResponse("OTHER")
                )

                intent = await self.agent.classify_user_intent(message)

                self.assertEqual(intent, self.agent.OTHER_INTENT)

    async def test_upcoming_meetings_excludes_cancelled_events(self) -> None:
        payload = {
            "meetings": [
                {
                    "eventId": "cancelled-id",
                    "subject": "Cancelled meeting",
                    "start": "2099-09-18T06:00:00Z",
                    "end": "2099-09-18T06:30:00Z",
                    "timeZone": "UTC",
                    "location": "",
                    "organizer": "",
                    "attendees": ["manager@contoso.com"],
                    "isCancelled": True,
                    "webLink": "",
                },
                {
                    "eventId": "active-id",
                    "subject": "Active meeting",
                    "start": "2099-09-18T07:00:00Z",
                    "end": "2099-09-18T07:30:00Z",
                    "timeZone": "UTC",
                    "location": "",
                    "organizer": "",
                    "attendees": ["manager@contoso.com"],
                    "isCancelled": False,
                    "webLink": "",
                },
            ]
        }
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse(json.dumps(payload))
        )

        result = await self.agent.list_upcoming_meetings(
            _FakeAuth(), "AGENTIC", self._manager_context()
        )

        self.assertEqual(
            [meeting["eventId"] for meeting in result["meetings"]],
            ["active-id"],
        )
        request = self.agent._http_client.requests[0]["json"]
        self.assertIn("Exclude deleted or cancelled meetings", request["instructions"])

    def test_meeting_cards_display_event_id(self) -> None:
        event_id = "AAMkAGI2-example-id"
        join_web_url = "https://teams.microsoft.com/l/meetup-join/example"
        list_card = build_upcoming_meetings_attachment(
            {
                "meetings": [
                    {
                        "eventId": event_id,
                        "subject": "Test meeting 3",
                        "start": "2026-09-18T06:00:00Z",
                        "end": "2026-09-18T06:30:00Z",
                        "joinWebUrl": join_web_url,
                    }
                ]
            }
        )

        serialized_list_card = json.dumps(list_card)
        self.assertIn("Meeting ID", serialized_list_card)
        self.assertIn(event_id, serialized_list_card)
        self.assertIn("Configure replies", serialized_list_card)
        self.assertNotIn("displayText", serialized_list_card)
        configure_action = list_card["content"]["body"][2]["items"][-1]["actions"][-1]
        self.assertEqual(configure_action["data"]["meetingId"], event_id)
        self.assertEqual(
            configure_action["data"]["scheduledStartTime"],
            "2026-09-18T06:00:00Z",
        )
        self.assertEqual(
            configure_action["data"]["scheduledEndTime"],
            "2026-09-18T06:30:00Z",
        )
        self.assertEqual(configure_action["data"]["joinWebUrl"], join_web_url)

    def test_meeting_list_command_supports_singular_and_plural_forms(self) -> None:
        self.assertTrue(_is_meeting_list_command("/meeting"))
        self.assertTrue(_is_meeting_list_command(" /MEETINGS "))
        self.assertFalse(_is_meeting_list_command("/meeting get event-id"))

    async def test_delegate_request_cannot_be_overridden_by_other_classification(
        self,
    ) -> None:
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse("OTHER")
        )

        intent = await self.agent.classify_user_intent(
            "帮我针对Test meeting 3，设置会议自动回复：问题1 digital worker "
            "sample什么时候发布，回答：2026年9月18日下午，具体时间待定。"
            "问题2：digital worker sample有哪些功能？回答：预定会议，代替我回答问题。"
        )

        self.assertEqual(intent, self.agent.CONFIGURE_DELEGATE_INTENT)
        request = self.agent._http_client.requests[0]["json"]
        self.assertIn("Meeting creation", request["instructions"])
        self.assertIn("unsupported", request["instructions"])

    def test_delegate_guidance_does_not_claim_configuration_succeeded(self) -> None:
        guidance = self.agent.meeting_delegate_configuration_guidance()

        self.assertIn("did not create a new meeting", guidance)
        self.assertIn("meetingId", guidance)
        self.assertNotIn("configured successfully", guidance.casefold())

    async def test_queries_only_calendar_mcp_for_upcoming_meetings(self) -> None:
        payload = {
            "meetings": [
                {
                    "eventId": "release-planning-id",
                    "subject": "Release planning",
                    "start": "2099-09-14T09:00:00Z",
                    "end": "2099-09-14T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "Teams meeting",
                    "organizer": "manager@contoso.com",
                    "attendees": ["meeting-agent@contoso.com"],
                    "isCancelled": False,
                    "webLink": "https://teams.microsoft.com/l/meetup-join/example",
                }
            ]
        }
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse(json.dumps(payload))
        )

        result = await self.agent.list_upcoming_meetings(
            _FakeAuth(), "AGENTIC", self._manager_context()
        )

        self.assertEqual(result["meetings"][0]["subject"], "Release planning")
        request = self.agent._http_client.requests[0]["json"]
        self.assertEqual(
            {tool["server_label"] for tool in request["tools"]},
            set(CALENDAR_MCP_SERVERS),
        )
        self.assertEqual(request["tool_choice"], "required")
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertIn("manager@contoso.com", request["instructions"])
        self.assertIn("signed-in Agent User", request["instructions"])
        meeting_schema = request["text"]["format"]["schema"]["properties"]["meetings"]["items"]
        self.assertIn("attendees", meeting_schema["properties"])

    async def test_enriches_calendar_location_and_links_from_graph(self) -> None:
        payload = {
            "meetings": [
                {
                    "eventId": "event/id=",
                    "subject": "Release planning",
                    "start": "2099-09-14T09:00:00Z",
                    "end": "2099-09-14T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "",
                    "organizer": "manager@contoso.com",
                    "attendees": ["meeting-agent@contoso.com"],
                    "isCancelled": False,
                    "webLink": "",
                    "joinWebUrl": "",
                }
            ]
        }
        client = _CalendarEventHttpClient(_IntentResponse(json.dumps(payload)))
        self.agent._http_client = client

        result = await self.agent.list_upcoming_meetings(
            _FakeAuth(), "AGENTIC", self._manager_context()
        )

        meeting = result["meetings"][0]
        self.assertEqual(meeting["location"], "Microsoft Teams Meeting")
        self.assertEqual(
            meeting["joinWebUrl"],
            "https://teams.microsoft.com/l/meetup-join/authoritative",
        )
        self.assertEqual(
            meeting["webLink"],
            "https://outlook.office.com/calendar/item/event",
        )
        self.assertIn("/me/events/event%2Fid%3D", client.event_requests[0]["url"])
        self.assertEqual(
            client.event_requests[0]["params"]["$select"],
            "location,onlineMeeting,onlineMeetingUrl,webLink",
        )

    async def test_preserves_calendar_values_when_graph_enrichment_fails(self) -> None:
        payload = {
            "meetings": [
                {
                    "eventId": "event-id",
                    "subject": "Release planning",
                    "start": "2099-09-14T09:00:00Z",
                    "end": "2099-09-14T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "Conference room",
                    "organizer": "manager@contoso.com",
                    "attendees": ["meeting-agent@contoso.com"],
                    "isCancelled": False,
                    "webLink": "https://outlook.office.com/calendar/item/fallback",
                    "joinWebUrl": "",
                }
            ]
        }
        self.agent._http_client = _UnavailableCalendarEventHttpClient(
            _IntentResponse(json.dumps(payload))
        )

        result = await self.agent.list_upcoming_meetings(
            _FakeAuth(), "AGENTIC", self._manager_context()
        )

        meeting = result["meetings"][0]
        self.assertEqual(meeting["location"], "Conference room")
        self.assertEqual(
            meeting["webLink"],
            "https://outlook.office.com/calendar/item/fallback",
        )

    async def test_excludes_upcoming_meeting_without_manager(self) -> None:
        payload = {
            "meetings": [
                {
                    "eventId": "manager-meeting-id",
                    "subject": "Manager sync",
                    "start": "2099-09-14T09:00:00Z",
                    "end": "2099-09-14T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "Teams meeting",
                    "organizer": "meeting-agent@contoso.com",
                    "attendees": ["manager@contoso.com"],
                    "isCancelled": False,
                    "webLink": "",
                },
                {
                    "eventId": "other-meeting-id",
                    "subject": "Peer sync",
                    "start": "2099-09-15T09:00:00Z",
                    "end": "2099-09-15T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "Teams meeting",
                    "organizer": "meeting-agent@contoso.com",
                    "attendees": ["peer@contoso.com"],
                    "isCancelled": False,
                    "webLink": "",
                },
                {
                    "eventId": "past-manager-meeting-id",
                    "subject": "Past manager sync",
                    "start": "2000-09-15T09:00:00Z",
                    "end": "2000-09-15T10:00:00Z",
                    "timeZone": "UTC",
                    "location": "Teams meeting",
                    "organizer": "meeting-agent@contoso.com",
                    "attendees": ["manager@contoso.com"],
                    "isCancelled": False,
                    "webLink": "",
                },
            ]
        }
        self.agent._http_client = _IntentHttpClient(
            _IntentResponse(json.dumps(payload))
        )

        result = await self.agent.list_upcoming_meetings(
            _FakeAuth(), "AGENTIC", self._manager_context()
        )

        self.assertEqual(
            [meeting["eventId"] for meeting in result["meetings"]],
            ["manager-meeting-id"],
        )

    def test_builds_upcoming_meetings_card_with_safe_link(self) -> None:
        join_web_url = "https://teams.microsoft.com/l/meetup-join/teams-link"
        attachment = build_upcoming_meetings_attachment(
            {
                "meetings": [
                    {
                        "subject": "Release planning",
                        "start": "2026-09-14T09:00:00",
                        "end": "2026-09-14T10:00:00",
                        "timeZone": "Pacific Standard Time",
                        "location": "Teams meeting",
                        "organizer": "Manager One",
                        "joinWebUrl": join_web_url,
                        "webLink": "https://outlook.cloud.microsoft/calendar/item/event-id",
                    }
                ]
            }
        )
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertIn("Release planning", serialized)
        self.assertIn("Action.OpenUrl", serialized)
        self.assertIn("Join Teams meeting", serialized)
        self.assertIn(join_web_url, serialized)
        self.assertNotIn("outlook.cloud.microsoft", serialized)

    def test_upcoming_meetings_card_falls_back_to_calendar_link(self) -> None:
        web_link = "https://outlook.cloud.microsoft/calendar/item/event-id"
        attachment = build_upcoming_meetings_attachment(
            {
                "meetings": [
                    {
                        "subject": "In-person planning",
                        "start": "2026-09-14T09:00:00",
                        "end": "2026-09-14T10:00:00",
                        "webLink": web_link,
                    }
                ]
            }
        )
        serialized = json.dumps(attachment)

        self.assertIn("Open meeting", serialized)
        self.assertIn(web_link, serialized)

    def test_upcoming_meetings_card_rejects_unsafe_link(self) -> None:
        attachment = build_upcoming_meetings_attachment(
            {
                "meetings": [
                    {
                        "subject": "Release planning",
                        "start": "2026-09-14T09:00:00",
                        "end": "2026-09-14T10:00:00",
                        "webLink": "javascript:alert(1)",
                    }
                ]
            }
        )

        self.assertNotIn("Action.OpenUrl", json.dumps(attachment))

    def test_meeting_delegate_card_has_rule_controls_and_toggles(self) -> None:
        attachment = build_meeting_delegate_attachment(
            {
                "meetingId": "meeting-1",
                "chatId": "meeting-chat-id",
                "delegationEnabled": False,
                "answerRules": [
                    {
                        "questions": ["When is the release?"],
                        "answer": "October 1.",
                        "enabled": False,
                    }
                ],
            }
        )

        serialized = json.dumps(attachment)
        self.assertIn('"type": "Input.Toggle"', serialized)
        self.assertIn("delegationEnabled", serialized)
        self.assertIn("ruleEnabled_0", serialized)
        self.assertIn("Add question", serialized)
        self.assertIn("Delete question", serialized)
        self.assertIn("Save", serialized)

        inputs = [
            item
            for container in attachment["content"]["body"]
            for item in container.get("items", [])
            if item.get("type", "").startswith("Input.")
        ]
        input_ids = {item.get("id") for item in inputs}
        self.assertNotIn("meetingId", input_ids)
        self.assertNotIn("chatId", input_ids)
        self.assertNotIn("subject", input_ids)
        save_action = attachment["content"]["actions"][-1]
        self.assertEqual(save_action["type"], "Action.Submit")
        self.assertEqual(save_action["data"]["meetingId"], "meeting-1")
        self.assertEqual(save_action["data"]["chatId"], "meeting-chat-id")
        self.assertEqual(save_action["data"]["msteams"]["type"], "messageBack")
        self.assertNotIn("displayText", save_action["data"]["msteams"])

    def test_extracts_meeting_id_from_natural_language_configuration(self) -> None:
        meeting_id = "AAMkADc21MGZjNjFhLWJmZjAtNGNmOS04NjkzLTYyNjljNzU1ZTFkZA=="

        self.assertEqual(
            extract_configuration_meeting_id(
                f"帮我配置meeting的自动回复：{meeting_id}"
            ),
            meeting_id,
        )
        self.assertEqual(
            extract_configuration_meeting_id(
                f"configure meeting auto-reply rule for this id:\n{meeting_id}"
            ),
            meeting_id,
        )

    def test_extracts_meeting_delegate_message_back_action(self) -> None:
        verb, data = get_submit_action(
            {
                "meetingId": "meeting-1",
                "question_0": "When?",
                "msteams": {
                    "value": {
                        "meetingDelegateAction": ADD_RULE_VERB,
                        "ruleCount": 1,
                    }
                },
            }
        )

        self.assertEqual(verb, ADD_RULE_VERB)
        self.assertEqual(data["meetingId"], "meeting-1")
        self.assertEqual(data["question_0"], "When?")

    def test_empty_nested_submit_metadata_does_not_replace_meeting_id(self) -> None:
        verb, data = get_submit_action(
            {
                "meetingId": "meeting-1",
                "question_0": "When?",
                "msteams": {
                    "value": {
                        "meetingDelegateAction": SAVE_RULES_VERB,
                        "meetingId": "",
                    }
                },
            }
        )

        self.assertEqual(verb, SAVE_RULES_VERB)
        self.assertEqual(data["meetingId"], "meeting-1")

    def test_missing_meeting_id_card_does_not_render_editable_form(self) -> None:
        attachment = build_meeting_delegate_attachment({"meetingId": ""})
        serialized = json.dumps(attachment)

        self.assertIn("Meeting ID is missing", serialized)
        self.assertNotIn("Input.Text", serialized)
        self.assertEqual(attachment["content"]["actions"], [])

    def test_recognizes_card_submit_text_and_display_echoes(self) -> None:
        self.assertTrue(is_submit_message(SUBMIT_TEXT))
        self.assertTrue(is_submit_message(SUBMIT_DISPLAY_TEXTS[SAVE_RULES_VERB]))
        self.assertTrue(is_submit_message("Save"))
        self.assertTrue(is_submit_message("Add question"))
        self.assertFalse(is_submit_message("Save the meeting notes"))

    def test_add_and_delete_question_preserve_submitted_values(self) -> None:
        submitted = {
            "meetingId": "meeting-1",
            "chatId": "meeting-chat-id",
            "delegationEnabled": "true",
            "ruleCount": 1,
            "question_0": "When is the release?",
            "answer_0": "October 1.",
            "ruleEnabled_0": "false",
        }

        added = rebuild_form_data(submitted, ADD_RULE_VERB)
        self.assertEqual(len(added["answerRules"]), 2)
        self.assertEqual(
            added["answerRules"][0]["questions"], ["When is the release?"]
        )
        self.assertFalse(added["answerRules"][0]["enabled"])

        deleted = rebuild_form_data(
            {
                **submitted,
                "ruleCount": 2,
                "question_1": "Is offline supported?",
                "answer_1": "Yes.",
                "ruleEnabled_1": "true",
                "removeIndex": 0,
            },
            REMOVE_RULE_VERB,
        )
        self.assertEqual(len(deleted["answerRules"]), 1)
        self.assertEqual(
            deleted["answerRules"][0]["questions"], ["Is offline supported?"]
        )

    async def test_updates_existing_meeting_reply_card(self) -> None:
        context = SimpleNamespace(
            activity=SimpleNamespace(reply_to_id="original-card-id"),
            update_activity=AsyncMock(),
            send_activity=AsyncMock(),
        )
        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"type": "AdaptiveCard", "version": "1.5"},
        }

        await _update_or_send_card(
            context,
            attachment,
        )

        context.update_activity.assert_awaited_once()
        updated = context.update_activity.await_args.args[0]
        self.assertEqual(updated.id, "original-card-id")
        self.assertEqual(updated.attachments[0].content, attachment["content"])
        context.send_activity.assert_not_awaited()

    async def test_sends_meeting_reply_card_without_original_activity_id(self) -> None:
        context = SimpleNamespace(
            activity=SimpleNamespace(reply_to_id=""),
            update_activity=AsyncMock(),
            send_activity=AsyncMock(),
        )
        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"type": "AdaptiveCard", "version": "1.5"},
        }

        await _update_or_send_card(
            context,
            attachment,
        )

        context.update_activity.assert_not_awaited()
        context.send_activity.assert_awaited_once()
        sent = context.send_activity.await_args.args[0]
        self.assertIsNone(sent.text)
        self.assertEqual(sent.attachments[0].content, attachment["content"])

    async def test_card_save_persists_rules_and_enable_switches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.agent._meeting_store = LocalFileMeetingDelegateStore(Path(directory))
            join_web_url = "https://teams.microsoft.com/l/meetup-join/example"
            attachment = await self.agent.handle_meeting_delegate_card_action(
                SAVE_RULES_VERB,
                {
                    "meetingId": "meeting-1",
                    "subject": "AZD Release Planning",
                    "joinWebUrl": join_web_url,
                    "scheduledStartTime": "2026-09-15T15:18:00Z",
                    "scheduledEndTime": "2026-09-15T15:19:00Z",
                    "delegationEnabled": "false",
                    "ruleCount": 2,
                    "question_0": "When is the release?",
                    "answer_0": "October 1.",
                    "ruleEnabled_0": "false",
                    "question_1": "Is offline supported?",
                    "answer_1": "Yes.",
                    "ruleEnabled_1": "true",
                },
                _FakeAuth(),
                "AGENTIC",
                self._manager_context(),
            )
            saved = await self.agent._meeting_store.get(
                "tenant-id", "agent-user-id", "meeting-1"
            )

            self.assertIn("Meeting reply rules saved.", json.dumps(attachment))
            self.assertFalse(saved["delegationEnabled"])
            self.assertEqual(saved["chatId"], "")
            self.assertEqual(saved["joinWebUrl"], join_web_url)
            self.assertEqual(saved["scheduledStartTime"], "2026-09-15T15:18:00Z")
            self.assertEqual(saved["scheduledEndTime"], "2026-09-15T15:19:00Z")
            self.assertEqual(len(saved["reactiveRules"]["answerRules"]), 2)
            self.assertFalse(saved["reactiveRules"]["answerRules"][0]["enabled"])
            self.assertTrue(saved["reactiveRules"]["answerRules"][1]["enabled"])

    async def test_card_save_resolves_join_url_and_persists_exact_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            join_web_url = "https://teams.microsoft.com/l/meetup-join/exact"
            http_client = _OnlineMeetingHttpClient(join_web_url)
            self.agent._http_client = http_client

            await self.agent.handle_meeting_delegate_card_action(
                SAVE_RULES_VERB,
                {
                    "meetingId": "calendar-event-id",
                    "joinWebUrl": join_web_url,
                    "delegationEnabled": "true",
                    "ruleCount": 1,
                    "question_0": "When is the release?",
                    "answer_0": "October 1.",
                    "ruleEnabled_0": "true",
                },
                _FakeAuth(),
                "AGENTIC",
                self._manager_context(),
            )

            by_online_id = await store.get(
                "tenant-id", "agent-user-id", "online-meeting-id"
            )
            by_thread_id = await store.get(
                "tenant-id", "agent-user-id", "meeting-thread-id"
            )
            self.assertEqual(by_online_id["meetingId"], "calendar-event-id")
            self.assertEqual(by_thread_id["meetingId"], "calendar-event-id")
            self.assertEqual(
                http_client.online_meeting_params["$filter"],
                f"JoinWebUrl eq '{join_web_url}'",
            )

    async def test_non_manager_card_save_does_not_persist_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.agent._meeting_store = LocalFileMeetingDelegateStore(Path(directory))
            context = self._manager_context()
            context.activity.from_property.aad_object_id = "someone-else"

            attachment = await self.agent.handle_meeting_delegate_card_action(
                SAVE_RULES_VERB,
                {
                    "meetingId": "meeting-1",
                    "chatId": "meeting-chat-id",
                    "delegationEnabled": "true",
                    "ruleCount": 1,
                    "question_0": "When is the release?",
                    "answer_0": "October 1.",
                    "ruleEnabled_0": "true",
                },
                _FakeAuth(),
                "AGENTIC",
                context,
            )
            saved = await self.agent._meeting_store.get(
                "tenant-id", "agent-user-id", "meeting-1"
            )

            self.assertIn("current Manager", json.dumps(attachment))
            self.assertIsNone(saved)

    async def test_card_save_allows_empty_question_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.agent._meeting_store = LocalFileMeetingDelegateStore(Path(directory))

            await self.agent.handle_meeting_delegate_card_action(
                SAVE_RULES_VERB,
                {
                    "meetingId": "meeting-1",
                    "chatId": "meeting-chat-id",
                    "delegationEnabled": "false",
                    "ruleCount": 1,
                    "question_0": "",
                    "answer_0": "",
                    "ruleEnabled_0": "true",
                },
                _FakeAuth(),
                "AGENTIC",
                self._manager_context(),
            )
            saved = await self.agent._meeting_store.get(
                "tenant-id", "agent-user-id", "meeting-1"
            )

            self.assertEqual(saved["reactiveRules"]["answerRules"], [])
            self.assertFalse(saved["delegationEnabled"])

    async def test_manager_can_configure_meeting_delegate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.agent._meeting_store = LocalFileMeetingDelegateStore(Path(directory))
            payload = {
                "meetingId": "meeting-1",
                "chatId": "meeting-chat-id",
                "subject": "AZD Release Planning",
                "answerRules": [
                    {
                        "questions": ["When is the release?"],
                        "answer": "The release is planned for October 1.",
                    }
                ],
            }

            result = await self.agent.process_user_message(
                f"/meeting_delegate configure {json.dumps(payload)}",
                _FakeAuth(),
                "AGENTIC",
                self._manager_context(),
            )
            saved = await self.agent._meeting_store.get(
                "tenant-id", "agent-user-id", "meeting-1"
            )

            self.assertIn("Meeting delegate configured", result)
            self.assertEqual(saved["managerObjectId"], "manager-object-id")
            self.assertEqual(saved["agentUserId"], "agent-user-id")

    async def test_non_manager_cannot_configure_meeting_delegate(self) -> None:
        context = self._manager_context()
        context.activity.from_property.aad_object_id = "someone-else"
        payload = {"meetingId": "meeting-1", "chatId": "meeting-chat-id"}

        result = await self.agent.process_user_message(
            f"/meeting_delegate configure {json.dumps(payload)}",
            _FakeAuth(),
            "AGENTIC",
            context,
        )

        self.assertIn("only this Digital Worker's current Manager", result)

    def test_detects_agent_mentions(self) -> None:
        context = self._participant_context()

        self.assertTrue(message_mentions_agent(context.activity, "@Agent question"))
        self.assertFalse(message_mentions_agent(context.activity, "Question without mention"))

    def test_detects_sdk_agent_mention_by_agentic_app_id(self) -> None:
        context = self._participant_context()
        context.activity.get_mentions = lambda: [
            SimpleNamespace(
                type="mention",
                mentioned=SimpleNamespace(id="agent-app-id"),
            )
        ]

        self.assertTrue(message_mentions_agent(context.activity, "Question for the agent"))

    def test_extracts_official_nested_teams_meeting_id_without_logging_raw_id(self) -> None:
        context = self._participant_context()
        context.activity.channel_data = {"meeting": {"id": "teams-meeting-secret"}}
        context.activity.conversation = SimpleNamespace(
            id="meeting-chat-secret",
            conversation_type="groupChat",
        )

        self.assertEqual(
            extract_meeting_id(context.activity),
            "teams-meeting-secret",
        )
        diagnostics = describe_meeting_activity(
            context.activity,
            "@Agent What is the bugbash date?",
        )
        serialized = json.dumps(diagnostics)
        self.assertEqual(diagnostics["channelDataKeys"], ["meeting"])
        self.assertEqual(diagnostics["conversationType"], "groupChat")
        self.assertTrue(diagnostics["mentioned"])
        self.assertNotIn("teams-meeting-secret", serialized)
        self.assertNotIn("meeting-chat-secret", serialized)

    async def test_meeting_chat_unknown_question_returns_out_of_scope_reply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            self.agent._http_client = _IntentHttpClient(
                _IntentResponse('{"ruleIndex":null}')
            )
            delegate = build_delegate(
                tenant_id="tenant-id",
                agent_user_id="agent-user-id",
                manager={"id": "manager-object-id"},
                request={
                    "meetingId": "meeting-1",
                    "chatId": "meeting-chat-id",
                    "answerRules": [
                        {
                            "questions": ["When is the release?"],
                            "answer": "October 1.",
                        }
                    ],
                },
            )
            await store.save(delegate)

            result = await self.agent.process_user_message(
                "@Agent Is offline deployment supported? meetingId=meeting-1",
                _FakeAuth(),
                "AGENTIC",
                self._participant_context(),
            )
            self.assertEqual(result, OUT_OF_SCOPE_REPLY)
            self.assertEqual(len(list(Path(directory).rglob("*.json"))), 1)

    async def test_meeting_chat_configured_question_returns_approved_answer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            self.agent._http_client = _IntentHttpClient(
                _IntentResponse('{"ruleIndex":0}')
            )
            await store.save(
                build_delegate(
                    tenant_id="tenant-id",
                    agent_user_id="agent-user-id",
                    manager={"id": "manager-object-id"},
                    request={
                        "meetingId": "meeting-1",
                        "chatId": "meeting-chat-id",
                        "answerRules": [
                            {
                                "questions": ["What is bugbash date?"],
                                "answer": "2026-09-20",
                            }
                        ],
                    },
                )
            )

            result = await self.agent.process_user_message(
                "@Agent What is the bugbash date? meetingId=meeting-1",
                _FakeAuth(),
                "AGENTIC",
                self._participant_context(),
            )

            self.assertEqual(result, "2026-09-20")
            request = self.agent._http_client.requests[0]["json"]
            request_input = json.loads(request["input"])
            self.assertEqual(
                request_input["standardQA"][0],
                {
                    "ruleIndex": 0,
                    "questions": ["What is bugbash date?"],
                    "answer": "2026-09-20",
                },
            )
            self.assertEqual(
                request_input["userQuestion"],
                "@Agent What is the bugbash date? meetingId=meeting-1",
            )
            self.assertNotIn("tools", request)
            self.assertNotIn("previous_response_id", request)
            self.assertEqual(request["text"]["format"]["type"], "json_schema")
            self.assertIn("Match by meaning, not keyword overlap", request["instructions"])
            self.assertIn(
                "last time normal changes can be merged",
                request["instructions"],
            )
            self.assertIn(
                "approved answer directly and fully answers",
                request["instructions"],
            )

    async def test_meeting_chat_resolves_teams_meeting_id_to_calendar_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            self.agent._http_client = _IntentHttpClient(
                _IntentResponse('{"ruleIndex":0}')
            )
            await store.save(
                build_delegate(
                    tenant_id="tenant-id",
                    agent_user_id="agent-user-id",
                    manager={"id": "manager-object-id"},
                    request={
                        "meetingId": "AAMk-calendar-event-id",
                        "answerRules": [
                            {
                                "questions": ["What is bugbash date?"],
                                "answer": "2026-09-20",
                            }
                        ],
                    },
                )
            )
            connector = _FakeTeamsConnector()
            context = self._participant_context()
            context.activity.channel_data = {
                "meeting": {"id": "teams-base64-meeting-id"}
            }
            context.services = _FakeServices({ConnectorClientBase: connector})

            result = await self.agent.process_user_message(
                "@Agent What is the bugbash date?",
                _FakeAuth(),
                "AGENTIC",
                context,
            )

            self.assertEqual(result, "2026-09-20")
            self.assertEqual(connector.meeting_id, "teams-base64-meeting-id")

    async def test_meeting_chat_resolves_delegate_by_unique_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            self.agent._http_client = _IntentHttpClient(
                _IntentResponse('{"ruleIndex":0}')
            )
            await store.save(
                build_delegate(
                    tenant_id="tenant-id",
                    agent_user_id="agent-user-id",
                    manager={"id": "manager-object-id"},
                    request={
                        "meetingId": "mailbox-scoped-calendar-event-id",
                        "scheduledStartTime": "2026-09-15T15:18:00+00:00",
                        "scheduledEndTime": "2026-09-15T15:19:00+00:00",
                        "answerRules": [
                            {
                                "questions": ["What is bugbash date?"],
                                "answer": "2026-09-20",
                            }
                        ],
                    },
                )
            )
            connector = _FakeTeamsConnector()
            context = self._participant_context()
            context.activity.channel_data = {
                "meeting": {"id": "teams-base64-meeting-id"}
            }
            context.services = _FakeServices({ConnectorClientBase: connector})

            result = await self.agent.process_user_message(
                "@Agent What is the bugbash date?",
                _FakeAuth(),
                "AGENTIC",
                context,
            )

            self.assertEqual(result, "2026-09-20")

    async def test_meeting_chat_resolves_delegate_by_persistent_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            await store.save(
                build_delegate(
                    tenant_id="tenant-id",
                    agent_user_id="agent-user-id",
                    manager={"id": "manager-object-id"},
                    request={
                        "meetingId": "mailbox-scoped-calendar-event-id",
                        "answerRules": [],
                    },
                )
            )

            await store.save_alias(
                "tenant-id",
                "agent-user-id",
                "teams-base64-meeting-id",
                "mailbox-scoped-calendar-event-id",
            )
            delegate = await store.get(
                "tenant-id", "agent-user-id", "teams-base64-meeting-id"
            )

            self.assertIsNotNone(delegate)
            self.assertEqual(
                delegate["meetingId"], "mailbox-scoped-calendar-event-id"
            )

    async def test_bind_command_links_current_meeting_chat_to_saved_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMeetingDelegateStore(Path(directory))
            self.agent._meeting_store = store
            await store.save(
                build_delegate(
                    tenant_id="tenant-id",
                    agent_user_id="agent-user-id",
                    manager={"id": "manager-object-id"},
                    request={
                        "meetingId": "mailbox-scoped-calendar-event-id",
                        "answerRules": [],
                    },
                )
            )
            context = self._manager_context()
            context.activity.channel_data = {
                "meeting": {"id": "teams-base64-meeting-id"}
            }
            context.activity.conversation.id = "meeting-chat-id"
            connector = _FakeTeamsConnector()
            context.services = _FakeServices({ConnectorClientBase: connector})

            result = await self.agent.process_user_message(
                "/meeting_delegate bind mailbox-scoped-calendar-event-id",
                _FakeAuth(),
                "AGENTIC",
                context,
            )
            delegate = await store.get(
                "tenant-id", "agent-user-id", "teams-base64-meeting-id"
            )

            self.assertEqual(
                result, "Meeting chat linked to the saved automatic reply rules."
            )
            self.assertIsNotNone(delegate)
            self.assertEqual(delegate["chatId"], "meeting-chat-id")

if __name__ == "__main__":
    unittest.main()
