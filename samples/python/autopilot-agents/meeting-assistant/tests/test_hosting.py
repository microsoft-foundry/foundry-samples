"""Offline HTTP ingress through AgentServer and the unmodified M365 adapter."""

from copy import deepcopy
from datetime import datetime
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from azure.ai.agentserver.activity import ActivityAgentServerHost
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.core.platform_headers import (
    ERROR_SOURCE, FOUNDRY_CALL_ID, SERVER_VERSION, SESSION_ID, USER_ID,
)
from microsoft_agents.hosting.core import ClaimsIdentity, MemoryStorage, RestChannelServiceClientFactory
from microsoft_agents.hosting.core.http import HttpResponse
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue

from agent.app import MeetingHandlers, build_app
from agent.hosting import MeetingActivityHost
from agent.workiq import WORKIQ_SCOPE
from test_meeting_assistant import INSTANCE, SETTINGS, TENANT


ENV = {
    "FOUNDRY_PROJECT_ENDPOINT": SETTINGS.project_endpoint,
    "AZURE_AI_MODEL_DEPLOYMENT_NAME": SETTINGS.model,
    "FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID": INSTANCE,
    "FOUNDRY_AGENT_TENANT_ID": TENANT,
    "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__TYPE": "AgenticUserAuthorization",
    "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES": WORKIQ_SCOPE,
}
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(kind):
    return json.loads((FIXTURES / f"meeting-{kind}.json").read_text(encoding="utf-8"))


class HostingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        def make_handlers(app, settings):
            self.handlers = MeetingHandlers(app, settings)
            return self.handlers

        with (
            patch.dict(os.environ, ENV, clear=True),
            patch("agent.app.configure_observability"),
            patch("agent.app.MeetingHandlers", side_effect=make_handlers),
        ):
            self.host = build_app()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.host), base_url="https://agent.test",
        )
        self.addAsyncCleanup(self.client.aclose)
        self.addAsyncCleanup(self.host.close_storage)

    async def test_actual_http_host_dispatches_native_meeting_events(self):
        processor = SimpleNamespace(start=AsyncMock(), end=AsyncMock())
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=processor)
        manager.__aexit__ = AsyncMock(return_value=False)
        connector, token_client = MagicMock(), MagicMock()
        connector.close = AsyncMock()
        token_client.close = AsyncMock()
        signature = inspect.signature(ClaimsIdentity)
        contexts = []
        previous = get_request_context()
        previous_values = previous.session_id, previous.user_id, previous.call_id

        @self.host.agent_app.before_turn
        async def capture_context(context, state):
            contexts.append(get_request_context())
            return True

        with (
            patch.object(self.handlers, "processor", return_value=manager),
            patch.object(
                self.host.agent_app.auth, "_start_or_continue_sign_in",
                new_callable=AsyncMock,
            ) as sign_in,
            patch.object(
                RestChannelServiceClientFactory, "create_connector_client",
                new_callable=AsyncMock, return_value=connector,
            ),
            patch.object(
                RestChannelServiceClientFactory, "create_user_token_client",
                new_callable=AsyncMock, return_value=token_client,
            ),
        ):
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: True)
            for kind in ("start", "end"):
                payload = fixture(kind)
                original = deepcopy(payload)
                response = await self.client.post(
                    "/activity/messages", json=payload,
                    headers={SESSION_ID: "synthetic-session", USER_ID: "synthetic-user",
                             FOUNDRY_CALL_ID: "synthetic-call"},
                )
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(response.headers[SESSION_ID], "synthetic-session")
                self.assertEqual(response.headers["x-agent-activity-id"], payload["id"])
                self.assertIn("azure-ai-agentserver-activity", response.headers[SERVER_VERSION])
                method = processor.start if kind == "start" else processor.end
                method.assert_awaited_once()
                meeting, chat_id = method.call_args.args
                model = MeetingStartEventValue if kind == "start" else MeetingEndEventValue
                self.assertIsInstance(meeting, model)
                self.assertEqual(meeting.join_url, payload["value"]["JoinUrl"])
                self.assertEqual(chat_id, payload["conversation"]["id"])
                timestamp = meeting.start_time if kind == "start" else meeting.end_time
                self.assertEqual(timestamp, datetime.fromisoformat(
                    payload["value"]["StartTime" if kind == "start" else "EndTime"],
                ))
                self.assertEqual(payload, original)
            self.assertEqual(sign_in.await_count, 2)
            self.assertTrue(all(call.args[2] == "AGENTIC" for call in sign_in.call_args_list))
        self.assertEqual(inspect.signature(ClaimsIdentity), signature)
        self.assertNotIn("is_authenticated", signature.parameters)
        self.assertIsInstance(self.host, ActivityAgentServerHost)
        for context in contexts:
            self.assertEqual(context.session_id, "synthetic-session")
            self.assertEqual(context.user_id, "synthetic-user")
            self.assertEqual(context.call_id, "synthetic-call")
        current = get_request_context()
        self.assertEqual((current.session_id, current.user_id, current.call_id), previous_values)

    async def test_incomplete_agentic_authorization_still_blocks_business_processing(self):
        connector, token_client = MagicMock(), MagicMock()
        connector.close = AsyncMock()
        token_client.close = AsyncMock()
        with (
            patch.object(self.handlers, "processor") as processor,
            patch.object(
                self.host.agent_app.auth, "_start_or_continue_sign_in",
                new_callable=AsyncMock,
            ) as sign_in,
            patch.object(
                RestChannelServiceClientFactory, "create_connector_client",
                new_callable=AsyncMock, return_value=connector,
            ),
            patch.object(
                RestChannelServiceClientFactory, "create_user_token_client",
                new_callable=AsyncMock, return_value=token_client,
            ),
        ):
            sign_in.return_value = SimpleNamespace(sign_in_complete=lambda: False)
            response = await self.client.post("/activity/messages", json=fixture("start"))
        self.assertEqual(response.status_code, 202, response.text)
        processor.assert_not_called()
        sign_in.assert_awaited_once()
        self.assertEqual(sign_in.call_args.args[2], "AGENTIC")

    async def test_malformed_json_is_rejected_before_the_m365_adapter(self):
        with patch.object(self.host.adapter, "process_request") as process:
            response = await self.client.post(
                "/activity/messages", content="{", headers={SESSION_ID: "synthetic-session"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(response.headers[SESSION_ID], "synthetic-session")
        process.assert_not_called()

    async def test_m365_errors_keep_status_headers_and_agentserver_error_shape(self):
        for status in (400, 401, 500):
            with patch.object(
                self.host.adapter, "process_request", new_callable=AsyncMock,
                return_value=HttpResponse(status, {"error": "Rejected"}, {"x-test-header": "kept"}),
            ) as process:
                response = await self.client.post("/activity/messages", json=fixture("start"))
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["x-test-header"], "kept")
            self.assertEqual(response.headers[ERROR_SOURCE], "upstream")
            self.assertEqual(response.json()["error"]["message"], "Rejected")
            self.assertEqual(
                response.json()["error"]["code"],
                "invalid_request" if status == 400 else "internal_error",
            )
            identity = process.call_args.args[0].get_claims_identity()
            self.assertTrue(identity.allow_anonymous)
            self.assertEqual(identity.claims, {})
            self.assertEqual(identity.authentication_type, "Anonymous")

    async def test_successful_m365_response_body_and_headers_are_preserved(self):
        body = {"result": "synthetic"}
        with patch.object(
            self.host.adapter, "process_request", new_callable=AsyncMock,
            return_value=HttpResponse(200, body, {"x-test-header": "kept"}),
        ):
            response = await self.client.post("/activity/messages", json=fixture("start"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), body)
        self.assertEqual(response.headers["x-test-header"], "kept")

    async def test_unexpected_adapter_failure_is_not_success_or_leaked_to_http(self):
        with patch.object(
            self.host.adapter, "process_request", new_callable=AsyncMock,
            side_effect=RuntimeError("private diagnostic detail"),
        ):
            response = await self.client.post("/activity/messages", json=fixture("start"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "internal_error")
        self.assertNotIn("private diagnostic detail", response.text)

    async def test_readiness_and_platform_headers_still_come_from_agentserver(self):
        response = await self.client.get("/readiness")
        self.assertEqual(response.status_code, 200)
        self.assertIn("azure-ai-agentserver-core", response.headers[SERVER_VERSION])

    async def test_hosted_storage_is_owned_and_closed_at_shutdown(self):
        store = MemoryStorage()
        store.aclose = AsyncMock()
        with (
            patch.dict(os.environ, {**ENV, "FOUNDRY_HOSTING_ENVIRONMENT": "test"}, clear=True),
            patch("agent.hosting.FoundryStorage", return_value=store) as factory,
        ):
            host = MeetingActivityHost(configure_observability=None)
        factory.assert_called_once_with()
        self.assertTrue(host.config.is_hosted)
        async with host.router.lifespan_context(host):
            store.aclose.assert_not_awaited()
        store.aclose.assert_awaited_once()
        await host.close_storage()
        store.aclose.assert_awaited_once()

    async def test_caller_owned_storage_is_not_closed(self):
        store = MemoryStorage()
        store.aclose = AsyncMock()
        with patch.dict(os.environ, ENV, clear=True):
            host = MeetingActivityHost(configure_observability=None, storage=store)
        await host.close_storage()
        store.aclose.assert_not_awaited()
