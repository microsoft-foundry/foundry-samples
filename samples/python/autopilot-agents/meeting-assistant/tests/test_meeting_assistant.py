"""Offline tests for Activity routing and agent-user Work IQ authentication."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from microsoft_agents.activity import Activity
from microsoft_teams.api.activities.event.meeting_start import MeetingStartEventValue
from pydantic import ValidationError

from agent.app import MeetingHandlers, Settings, build_app, on_error, register_handlers
from agent.request_logging import ActivityPayloadLoggingMiddleware
from agent.workiq import WORKIQ_SCOPE, WorkIQError

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"
AGENT_USER = "33333333-3333-3333-3333-333333333333"
INSTANCE = "44444444-4444-4444-4444-444444444444"
SETTINGS = Settings("https://example.test/project", "model")


def activity(**changes) -> Activity:
    values = {
        "type": "message", "channelId": "msteams",
        "text": "Summarize the planning meeting",
        "from": {"aadObjectId": USER},
        "recipient": {
            "role": "agenticUser", "agenticUserId": AGENT_USER,
            "agenticAppId": INSTANCE, "tenantId": TENANT,
        },
        "conversation": {"conversationType": "personal", "tenantId": TENANT},
    }
    values.update(changes)
    values["conversation"] = {"id": "synthetic-dm", **values["conversation"]}
    return Activity.model_validate(values)


class ConfigurationTests(unittest.TestCase):
    def test_settings_need_no_user_or_tenant_configuration(self):
        env = {
            "FOUNDRY_PROJECT_ENDPOINT": SETTINGS.project_endpoint,
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(Settings.from_env(), SETTINGS)
            for flag in (
                "MEETING_LOG_ACTIVITY_PAYLOADS",
                "MEETING_LOG_WORKIQ_PAYLOADS",
            ):
                os.environ[flag] = "yes"
                with self.assertRaises(ValueError):
                    Settings.from_env()
                os.environ[flag] = "false"
            os.environ["MEETING_ENABLE_AI_INSIGHTS"] = "true"
            self.assertEqual(Settings.from_env(), SETTINGS)
            os.environ["MEETING_LOG_ACTIVITY_PAYLOADS"] = "true"
            self.assertTrue(Settings.from_env().log_activity_payloads)
            os.environ["MEETING_LOG_WORKIQ_PAYLOADS"] = "true"
            self.assertTrue(Settings.from_env().log_workiq_payloads)
            os.environ["FOUNDRY_PROJECT_ENDPOINT"] = ""
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_installed_sdk_constructs_agentic_authorization_handler(self):
        env = {
            "FOUNDRY_PROJECT_ENDPOINT": SETTINGS.project_endpoint,
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
            "FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID": INSTANCE,
            "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__TYPE": "AgenticUserAuthorization",
            "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES": WORKIQ_SCOPE,
        }
        with patch.dict(os.environ, env, clear=True), patch("agent.app.configure_observability"):
            host = build_app()
            self.assertEqual(list(host.agent_app.auth._handlers), ["AGENTIC"])
            self.assertFalse(any(
                middleware.cls is ActivityPayloadLoggingMiddleware for middleware in host.user_middleware
            ))
            os.environ["MEETING_LOG_ACTIVITY_PAYLOADS"] = "true"
            with self.assertLogs("agent.app", level="WARNING"):
                host = build_app()
            self.assertIs(host.user_middleware[0].cls, ActivityPayloadLoggingMiddleware)
            os.environ["MEETING_LOG_WORKIQ_PAYLOADS"] = "true"
            with self.assertLogs("agent.app", level="WARNING") as logs:
                build_app()
            self.assertIn("Unredacted Work IQ payload logging is enabled", "\n".join(logs.output))


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_validation_logging_omits_payload_values(self):
        context = SimpleNamespace(activity=activity(name="application/vnd.microsoft.meetingStart"))
        with self.assertLogs("agent.app", level="ERROR") as logs:
            try:
                MeetingStartEventValue.model_validate({"Title": "private-title-not-for-diagnostics"})
            except ValidationError as error:
                await on_error(context, error)
        output = "\n".join(logs.output)
        self.assertIn("MeetingStartEventValue", output)
        self.assertIn("StartTime", output)
        self.assertNotIn("private-title-not-for-diagnostics", output)

    async def test_workiq_error_logging_reports_safe_inner_code(self):
        context = SimpleNamespace(activity=activity())
        request_id = "11111111-2222-3333-4444-555555555555"
        with self.assertLogs("agent.app", level="ERROR") as logs:
            await on_error(context, WorkIQError(
                403, "Forbidden", "GraphAccessToTranscriptsDisabled", request_id=request_id,
            ))
        self.assertIn("GraphAccessToTranscriptsDisabled", "\n".join(logs.output))
        self.assertIn(request_id, "\n".join(logs.output))

    async def test_grouped_mcp_errors_keep_safe_diagnostics(self):
        context = SimpleNamespace(activity=activity())
        error = ExceptionGroup("private request context", [
            ExceptionGroup("private MCP context", [
                WorkIQError(403, "Forbidden", "GraphAccessToTranscriptsDisabled"),
            ]),
        ])
        with self.assertLogs("agent.app", level="ERROR") as logs:
            await on_error(context, error)
        output = "\n".join(logs.output)
        self.assertIn("status=403", output)
        self.assertIn("GraphAccessToTranscriptsDisabled", output)
        self.assertNotIn("private", output)

    async def test_registration_only_wires_existing_handlers(self):
        app = SimpleNamespace(error=Mock(), add_route=Mock(), before_turn=Mock())
        handlers = MeetingHandlers(app, SETTINGS)
        with (
            patch.object(handlers, "clients") as clients,
            patch("agent.app.TeamsAgentExtension") as extension,
        ):
            register_handlers(app, handlers)
        extension.assert_called_once_with(app)
        extension.return_value.meetings.start.assert_called_once_with(auth_handlers=["AGENTIC"])
        extension.return_value.meetings.start.return_value.assert_called_once_with(handlers.on_meeting_start)
        extension.return_value.meetings.end.assert_called_once_with(auth_handlers=["AGENTIC"])
        extension.return_value.meetings.end.return_value.assert_called_once_with(handlers.on_meeting_end)
        app.error.assert_called_once_with(on_error)
        routes = app.add_route.call_args_list
        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[0].args[1], handlers.on_recording_available)
        self.assertEqual(routes[1].args[1], handlers.on_added_to_meeting)
        self.assertTrue(all(route.kwargs["auth_handlers"] == ["AGENTIC"] for route in routes[:2]))
        self.assertNotIn("auth_handlers", routes[-1].kwargs)
        clients.assert_not_called()

    async def test_free_form_messages_are_ignored_without_auth_or_reply(self):
        routes = []
        app = SimpleNamespace(
            error=lambda handler: handler, before_turn=lambda handler: handler,
            add_route=lambda selector, handler, **kwargs: routes.append((selector, handler, kwargs)),
            auth=SimpleNamespace(exchange_token=AsyncMock()),
        )
        register_handlers(app, MeetingHandlers(app, SETTINGS))
        for kind in ("personal", "groupChat"):
            context = SimpleNamespace(
                activity=activity(conversation={"conversationType": kind, "tenantId": TENANT}),
                send_activity=AsyncMock(),
            )
            handler = next(route[1] for route in routes if route[0](context))
            self.assertEqual(handler.__name__, "ignore")
            await handler(context, None)
            context.send_activity.assert_not_awaited()
        app.auth.exchange_token.assert_not_awaited()

    async def test_missing_token_never_opens_workiq_or_model(self):
        auth = SimpleNamespace(exchange_token=AsyncMock(return_value=SimpleNamespace(token=None)))
        handlers = MeetingHandlers(SimpleNamespace(auth=auth), SETTINGS)
        context = SimpleNamespace(activity=activity(), send_activity=AsyncMock())
        with patch("agent.app.streamable_http_client") as transport:
            with self.assertRaisesRegex(RuntimeError, "no token"):
                async with handlers.clients(context):
                    self.fail("Clients must not open without a token.")
        transport.assert_not_called()
        auth.exchange_token.assert_awaited_once_with(
            context, scopes=[WORKIQ_SCOPE], auth_handler_id="AGENTIC",
        )


if __name__ == "__main__":
    unittest.main()
