"""Sample HTTP ingress: native meeting dispatch and AGENTIC authorization."""

from datetime import datetime
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from microsoft_agents.hosting.core import RestChannelServiceClientFactory
from microsoft_teams.api.activities.event.meeting_end import MeetingEndEventValue
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue

from agent.app import MeetingHandlers, build_app
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


class HttpIngressTests(IsolatedAsyncioTestCase):
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
        lifespan = self.host.router.lifespan_context(self.host)
        await lifespan.__aenter__()
        self.addAsyncCleanup(lifespan.__aexit__, None, None, None)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.host), base_url="https://agent.test",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_http_ingress_dispatches_native_meeting_events(self):
        processor = SimpleNamespace(start=AsyncMock(), end=AsyncMock())
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=processor)
        manager.__aexit__ = AsyncMock(return_value=False)
        connector, token_client = MagicMock(), MagicMock()
        connector.close = AsyncMock()
        token_client.close = AsyncMock()
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
                response = await self.client.post(
                    "/activity/messages", json=payload,
                )
                self.assertEqual(response.status_code, 202, response.text)
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
            self.assertEqual(sign_in.await_count, 2)
            self.assertTrue(all(call.args[2] == "AGENTIC" for call in sign_in.call_args_list))

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
