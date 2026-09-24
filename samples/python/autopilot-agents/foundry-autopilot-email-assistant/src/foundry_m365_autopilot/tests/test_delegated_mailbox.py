from __future__ import annotations

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from azure.core.exceptions import ResourceNotFoundError

from foundry_m365_autopilot.agent import FoundryDigitalWorkerAgent
from foundry_m365_autopilot.activity_context import build_activity_context_attachment
from foundry_m365_autopilot.capabilities import build_capabilities_attachment
from foundry_m365_autopilot.monitoring_status import (
    build_monitoring_clarification_attachment,
    build_monitoring_configuration_attachment,
    build_monitoring_status_attachment,
)
from foundry_m365_autopilot.monitoring_config_cards import (
    CONFIGURE_FORM_SUBMIT_TEXT,
    CONFIGURE_FORM_VERB,
    EDIT_JSON_SUBMIT_TEXT,
    EDIT_JSON_VERB,
    build_form_configuration_arguments,
    build_json_configuration_arguments,
    build_monitoring_form_attachment,
    build_monitoring_json_attachment,
    get_execute_action,
    get_submit_action,
)
from foundry_m365_autopilot.tools.forwarded_email import (
    build_manager_notification,
    normalize_forwarded_sent_at,
    normalize_mail_summary,
    parse_forwarded_email,
)
from foundry_m365_autopilot.tools.graph import (
    GRAPH_SCOPE,
    decode_graph_token_claims,
    get_agent_manager,
)
from foundry_m365_autopilot.tools.mail_monitoring import (
    AzureBlobMailMonitoringStore,
    LocalFileMailMonitoringStore,
    MailFilterValidationError,
    describe_filter,
    matches_filter,
    normalize_filter,
)
from foundry_m365_autopilot.tools.proactive_messaging import send_proactive_message
from foundry_m365_autopilot.tools.read_delegated_mailbox_inbox import (
    execute as read_delegated_mailbox_inbox,
)
from foundry_m365_autopilot.tools.registry import dispatch, extract_function_calls
from foundry_m365_autopilot.tools.runtime import ToolRuntime


class _FakeAuth:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    async def exchange_token(self, context, *, scopes, auth_handler_id):
        self.scopes = scopes
        return SimpleNamespace(token="graph-token")


class _FakeResponse:
    status_code = 200
    text = ""
    headers = {}

    def json(self):
        return {
            "value": [
                {
                    "id": "message-1",
                    "subject": "Delegated message",
                    "receivedDateTime": "2026-09-02T00:00:00Z",
                }
            ]
        }


class _FakeHttpClient:
    def __init__(self) -> None:
        self.url = ""
        self.params = {}
        self.headers = {}

    async def get(self, url, *, params, headers):
        self.url = url
        self.params = params
        self.headers = headers
        return _FakeResponse()


class _ManagerResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "id": "agent-user-id",
            "userPrincipalName": "autopilotdemo0829@activityprotocol66.onmicrosoft.com",
            "manager": {
                "id": "manager-object-id",
                "displayName": "Huajie Zhang",
                "userPrincipalName": "HuajieZhang@activityprotocol66.onmicrosoft.com",
                "mail": "HuajieZhang@activityprotocol66.onmicrosoft.com",
            },
        }


class _ManagerHttpClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get(self, url, *, params, headers):
        self.calls += 1
        self.url = url
        self.params = params
        self.headers = headers
        return _ManagerResponse()


class _FakeMonitoringStore:
    def __init__(self, config=None, conversation=None) -> None:
        self.config = config
        self.conversation = conversation

    async def get(self, tenant_id, agent_user_id):
        return self.config

    async def get_manager_conversation(self, tenant_id, agent_user_id):
        return self.conversation

    async def save_manager_conversation(
        self, tenant_id, agent_user_id, conversation
    ):
        self.conversation = conversation


class _FakeBlobDownloader:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def readall(self):
        return self.content


class _FakeBlobClient:
    def __init__(self, blobs: dict[str, bytes], name: str) -> None:
        self.blobs = blobs
        self.name = name

    async def download_blob(self):
        if self.name not in self.blobs:
            raise ResourceNotFoundError("Blob does not exist")
        return _FakeBlobDownloader(self.blobs[self.name])

    async def upload_blob(self, data, *, overwrite, content_settings):
        self.blobs[self.name] = data.encode("utf-8")


class _FakeContainerClient:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def get_blob_client(self, name: str):
        return _FakeBlobClient(self.blobs, name)


class _ErrorResponse:
    status_code = 404
    text = ""
    headers = {"request-id": "graph-request-id"}

    def json(self):
        return {
            "error": {
                "code": "ErrorItemNotFound",
                "message": "Default folder Inbox not found.",
            }
        }


class _DiagnosticHttpClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def get(self, url, *, params, headers):
        self.urls.append(url)
        return _ErrorResponse()


class _ResponsesResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self.payload


class _QueuedResponsesClient:
    def __init__(self, *responses: _ResponsesResponse) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    async def post(self, url, *, json, headers):
        # Capture a value copy because stale-response recovery mutates the
        # original request dictionary before retrying it.
        self.requests.append(
            {
                "url": url,
                "json": copy.deepcopy(json),
                "headers": dict(headers),
            }
        )
        return self.responses.pop(0)


def _unsigned_token(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"header.{encoded.decode()}.signature"


def _tool_runtime(*, auth, context, http_client, store=None) -> ToolRuntime:
    return ToolRuntime(
        auth=auth,
        auth_handler_name="AGENTIC",
        context=context,
        http_client=http_client,
        mail_monitor_store=store or _FakeMonitoringStore(),
        manager_cache={},
    )


class DelegatedMailboxTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _responses_agent(*responses: _ResponsesResponse):
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _QueuedResponsesClient(*responses)
        agent._deployment = "gpt-5-mini"
        agent._responses_endpoint = "https://example.test/openai/v1/responses"
        agent._endpoint = None
        agent._api_version = "test-version"
        agent._api_key = "test-key"
        agent._build_responses_tools = AsyncMock(
            return_value=[
                {"type": "mcp", "server_label": "mcp_TeamsServer"},
                {"type": "function", "name": "local_tool"},
            ]
        )
        agent._load_previous_response_id = lambda conversation_id: None
        agent._save_response_id = Mock()
        agent._clear_previous_response_id = Mock()
        return agent

    async def test_reads_explicit_delegated_inbox(self) -> None:
        client = _FakeHttpClient()
        auth = _FakeAuth()

        result = await read_delegated_mailbox_inbox(
            {"user_principal_name": "owner@contoso.com", "top": 3},
            _tool_runtime(
                auth=auth,
                context=object(),
                http_client=client,
            ),
        )

        self.assertEqual(auth.scopes, [GRAPH_SCOPE])
        self.assertIn(
            "/users/owner%40contoso.com/mailFolders('Inbox')/messages", client.url
        )
        self.assertEqual(client.params["$top"], "3")
        self.assertEqual(client.headers["Authorization"], "Bearer graph-token")
        self.assertEqual(result["mailbox"], "owner@contoso.com")
        self.assertEqual(result["folder"], "Inbox")
        self.assertEqual(result["messages"][0]["subject"], "Delegated message")

    async def test_rejects_missing_mailbox_upn(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid delegated mailbox"):
            await read_delegated_mailbox_inbox(
                {"user_principal_name": "not-a-upn", "top": 5},
                _tool_runtime(
                    auth=_FakeAuth(),
                    context=object(),
                    http_client=_FakeHttpClient(),
                ),
            )

    def test_extracts_only_supported_function_calls(self) -> None:
        calls = extract_function_calls(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "read_delegated_mailbox_inbox",
                        "call_id": "call-1",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call",
                        "name": "unknown_tool",
                        "call_id": "call-2",
                    },
                ]
            }
        )

        self.assertEqual([call["call_id"] for call in calls], ["call-1"])

    async def test_builds_flat_mcp_and_local_function_tool_bundle(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._build_mcp_tools = AsyncMock(
            return_value=[{"type": "mcp", "server_label": "mcp_TeamsServer"}]
        )

        tools = await agent._build_responses_tools(
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
        )

        self.assertEqual(
            [tool["type"] for tool in tools],
            ["mcp", "function", "function", "function", "function", "function"],
        )
        self.assertEqual(
            [tool.get("name") for tool in tools[1:]],
            [
                "read_delegated_mailbox_inbox",
                "configure_mail_monitoring",
                "enable_mail_monitoring",
                "get_mail_monitoring_status",
                "disable_mail_monitoring",
            ],
        )

    async def test_filters_mcp_servers_by_explicit_allowlist(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._mcp_servers = [
            {"mcpServerName": "mcp_TeamsServer", "url": "https://teams.test"},
            {"mcpServerName": "mcp_MailTools", "url": "https://mail.test"},
        ]
        agent._acquire_mcp_token = AsyncMock(return_value="mcp-token")

        ordinary_chat_tools = await agent._build_mcp_tools(
            _FakeAuth(),
            "AGENTIC",
            object(),
            mcp_server_labels=(),
        )
        teams_workflow_tools = await agent._build_mcp_tools(
            _FakeAuth(),
            "AGENTIC",
            object(),
            mcp_server_labels=("mcp_TeamsServer",),
        )

        self.assertEqual(ordinary_chat_tools, [])
        self.assertEqual(
            [tool["server_label"] for tool in teams_workflow_tools],
            ["mcp_TeamsServer"],
        )

    async def test_builds_teams_only_tool_bundle_for_forwarded_email(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._build_mcp_tools = AsyncMock(
            return_value=[{"type": "mcp", "server_label": "mcp_TeamsServer"}]
        )

        tools = await agent._build_responses_tools(
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
            mcp_server_labels=("mcp_TeamsServer",),
            include_local_function_tools=False,
        )

        self.assertEqual(
            tools,
            [{"type": "mcp", "server_label": "mcp_TeamsServer"}],
        )

    async def test_correlates_local_function_outputs_by_call_id(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._execute_custom_function_call = AsyncMock(
            side_effect=[{"first": True}, {"second": True}]
        )

        outputs = await agent._execute_local_function_calls(
            [
                {"name": "first_tool", "call_id": "call-1"},
                {"name": "second_tool", "call_id": "call-2"},
            ],
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
        )

        self.assertEqual(
            [output["call_id"] for output in outputs], ["call-1", "call-2"]
        )
        self.assertEqual(json.loads(outputs[0]["output"]), {"first": True})
        self.assertEqual(json.loads(outputs[1]["output"]), {"second": True})

    async def test_mcp_call_completes_server_side_without_local_dispatch(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse(
                {
                    "id": "response-mcp",
                    "output": [
                        {
                            "type": "mcp_call",
                            "server_label": "mcp_TeamsServer",
                            "name": "SendChatMessage",
                            "error": None,
                        },
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "Message sent."}
                            ],
                        },
                    ],
                }
            )
        )
        agent._execute_custom_function_call = AsyncMock()

        result = await agent._invoke_responses_api(
            input_text="Send a Teams message",
            conversation_id="conversation-mcp",
            instructions="Use Teams when requested.",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
            expected_mcp_server_label="mcp_TeamsServer",
        )

        self.assertEqual(result, "Message sent.")
        self.assertEqual(len(agent._http_client.requests), 1)
        agent._execute_custom_function_call.assert_not_awaited()

    async def test_local_function_call_posts_correlated_continuation(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse(
                {
                    "id": "response-tool-call",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "read_delegated_mailbox_inbox",
                            "call_id": "call-mailbox",
                            "arguments": '{"user_principal_name":"owner@contoso.com","top":3}',
                        }
                    ],
                }
            ),
            _ResponsesResponse(
                {
                    "id": "response-final",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "Three messages."}
                            ],
                        }
                    ],
                }
            ),
        )
        agent._execute_custom_function_call = AsyncMock(
            return_value={"messages": [{"id": "message-1"}]}
        )

        result = await agent._invoke_responses_api(
            input_text="Read the delegated mailbox",
            conversation_id="conversation-local",
            instructions="Use the delegated mailbox tool.",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
        )

        self.assertEqual(result, "Three messages.")
        self.assertEqual(len(agent._http_client.requests), 2)
        continuation = agent._http_client.requests[1]["json"]
        self.assertEqual(continuation["previous_response_id"], "response-tool-call")
        self.assertEqual(
            continuation["input"][0]["type"], "function_call_output"
        )
        self.assertEqual(continuation["input"][0]["call_id"], "call-mailbox")
        self.assertEqual(
            json.loads(continuation["input"][0]["output"]),
            {"messages": [{"id": "message-1"}]},
        )

    async def test_configure_monitoring_sends_confirmation_card(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse(
                {
                    "id": "response-configure",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "configure_mail_monitoring",
                            "call_id": "call-configure",
                            "arguments": "{}",
                        }
                    ],
                }
            )
        )
        agent._execute_custom_function_call = AsyncMock(
            return_value={
                "enabled": True,
                "filterDescription": "主题包含“important”",
                "sourceText": "监控标题包含 important 的邮件",
            }
        )
        context = SimpleNamespace(send_activity=AsyncMock())

        result = await agent._invoke_responses_api(
            input_text="设置邮件监控",
            conversation_id="conversation-configure",
            instructions="Configure monitoring when the rule is complete.",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=context,
        )

        self.assertEqual(result, "")
        self.assertEqual(len(agent._http_client.requests), 1)
        context.send_activity.assert_awaited_once()
        activity = context.send_activity.await_args.args[0]
        self.assertEqual(
            activity.attachments[0].content_type,
            "application/vnd.microsoft.card.adaptive",
        )
        self.assertIn(
            "Email monitoring enabled",
            json.dumps(activity.attachments[0].content),
        )
        agent._save_response_id.assert_not_called()
        agent._clear_previous_response_id.assert_called_once_with(
            "conversation-configure"
        )

    async def test_expired_previous_response_retries_without_cached_id(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse(
                {
                    "error": {"code": "previous_response_not_found"},
                },
                status_code=400,
            ),
            _ResponsesResponse(
                {
                    "id": "response-retried",
                    "output_text": "Recovered.",
                }
            ),
        )
        agent._load_previous_response_id = lambda conversation_id: "stale-response"
        agent._clear_previous_response_id = Mock()

        result = await agent._invoke_responses_api(
            input_text="Continue",
            conversation_id="conversation-stale",
            instructions="Continue safely.",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
        )

        self.assertEqual(result, "Recovered.")
        self.assertEqual(len(agent._http_client.requests), 2)
        self.assertEqual(
            agent._http_client.requests[0]["json"]["previous_response_id"],
            "stale-response",
        )
        self.assertNotIn(
            "previous_response_id", agent._http_client.requests[1]["json"]
        )
        agent._clear_previous_response_id.assert_called_once_with(
            "conversation-stale"
        )

    async def test_pending_tool_previous_response_retries_without_cached_id(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse(
                {
                    "error": {
                        "message": "No tool output found for function call call-configure.",
                        "type": "invalid_request_error",
                        "param": "input",
                        "code": None,
                    }
                },
                status_code=400,
            ),
            _ResponsesResponse(
                {
                    "id": "response-retried",
                    "output_text": "Recovered.",
                }
            ),
        )
        agent._load_previous_response_id = lambda conversation_id: "pending-tool-call"

        result = await agent._invoke_responses_api(
            input_text="Reset my monitoring rule",
            conversation_id="conversation-pending-tool",
            instructions="Configure monitoring safely.",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=object(),
        )

        self.assertEqual(result, "Recovered.")
        self.assertEqual(len(agent._http_client.requests), 2)
        self.assertEqual(
            agent._http_client.requests[0]["json"]["previous_response_id"],
            "pending-tool-call",
        )
        self.assertNotIn(
            "previous_response_id", agent._http_client.requests[1]["json"]
        )
        agent._clear_previous_response_id.assert_called_once_with(
            "conversation-pending-tool"
        )

    async def test_unknown_function_does_not_read_delegated_mailbox(self) -> None:
        result = await dispatch(
            "unknown_tool",
            "{}",
            _tool_runtime(
                auth=_FakeAuth(),
                context=object(),
                http_client=_FakeHttpClient(),
            ),
        )

        self.assertEqual(result["error"]["code"], "unsupported_tool")

    def test_decodes_only_safe_graph_token_claims(self) -> None:
        token = _unsigned_token(
            {
                "aud": "00000003-0000-0000-c000-000000000000",
                "oid": "agent-user-object-id",
                "preferred_username": "agent@contoso.com",
                "scp": "Mail.Read.Shared User.Read",
                "secret": "must-not-be-returned",
            }
        )

        diagnostics = decode_graph_token_claims(token)

        self.assertTrue(diagnostics["has_mail_read_shared"])
        self.assertEqual(diagnostics["oid"], "agent-user-object-id")
        self.assertNotIn("secret", diagnostics)
        self.assertNotIn(token, json.dumps(diagnostics))

    async def test_failed_read_returns_staged_graph_diagnostics(self) -> None:
        token = _unsigned_token(
            {
                "aud": "00000003-0000-0000-c000-000000000000",
                "oid": "agent-user-object-id",
                "scp": "Mail.Read.Shared",
            }
        )
        client = _DiagnosticHttpClient()
        auth = _FakeAuth()

        async def exchange_token(context, *, scopes, auth_handler_id):
            return SimpleNamespace(token=token)

        auth.exchange_token = exchange_token
        result = await read_delegated_mailbox_inbox(
            {"user_principal_name": "owner@contoso.com", "top": 3},
            _tool_runtime(
                auth=auth,
                context=object(),
                http_client=client,
            ),
        )

        self.assertEqual(result["error"]["code"], "ErrorItemNotFound")
        self.assertTrue(result["diagnostics"]["token"]["has_mail_read_shared"])
        self.assertEqual(
            [probe["name"] for probe in result["diagnostics"]["probes"]],
            ["current_user", "current_user_inbox", "target_user", "target_inbox"],
        )
        self.assertEqual(len(client.urls), 5)

    def test_parses_standard_outlook_forward(self) -> None:
        result = parse_forwarded_email(
            """
            <div>FYI</div>
            <div>From: Huajie Zhang &lt;huajiezhang@microsoft.com&gt;</div>
            <div>Sent: Wednesday, September 2, 2026 9:00 AM</div>
            <div>To: Huajie Zhang &lt;HuajieZhang@activityprotocol66.onmicrosoft.com&gt;</div>
            <div>Subject: Important request</div>
            <p>Please review the attached proposal.</p>
            """
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["sender"], "huajiezhang@microsoft.com")
        self.assertEqual(result["subject"], "Important request")
        self.assertIn("Please review", result["body"])

    def test_parses_plain_text_activity_forward_without_losing_angle_address(self) -> None:
        result = parse_forwarded_email(
            "\nFrom: Huajie Zhang <huajiezhang@microsoft.com>\n"
            "Sent: Thursday, September 3, 2026 2:01:08 PM (UTC+08:00)\n"
            "To: Huajie Zhang <HuajieZhang@activityprotocol66.onmicrosoft.com>\n"
            "Subject: Email test 090304\n\n"
            "Hello huajie, this is a test email."
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["sender"], "huajiezhang@microsoft.com")
        self.assertEqual(result["subject"], "Email test 090304")
        self.assertEqual(result["body"], "Hello huajie, this is a test email.")

    async def test_resolves_and_caches_manager_per_agent_user(self) -> None:
        client = _ManagerHttpClient()
        manager_cache = {}
        context = SimpleNamespace(
            activity=SimpleNamespace(
                recipient=SimpleNamespace(
                    agentic_user_id="agent-user-id",
                    agentic_app_id="agent-app-id",
                )
            )
        )

        first = await get_agent_manager("graph-token", context, client, manager_cache)
        second = await get_agent_manager("graph-token", context, client, manager_cache)

        self.assertEqual(first["id"], "manager-object-id")
        self.assertEqual(
            first["userPrincipalName"],
            "HuajieZhang@activityprotocol66.onmicrosoft.com",
        )
        self.assertEqual(second, first)
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.url, "https://graph.microsoft.com/v1.0/me")
        self.assertIn("manager", client.params["$expand"])

    async def test_allowed_manager_forward_sends_proactive_summary(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        agent._clear_previous_response_id = Mock()
        agent._mail_monitor_store = _FakeMonitoringStore(
            {
                "version": "1.0",
                "enabled": True,
                "managerObjectId": "manager-object-id",
                "filter": {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "originalSender.address",
                            "operator": "equals",
                            "value": "huajiezhang@microsoft.com",
                        }
                    ],
                },
            },
            conversation={"version": "1.0", "conversation": {}},
        )
        agent._invoke_responses_api = AsyncMock(return_value="季度报告需要经理审阅。")
        notification = SimpleNamespace(
            email=SimpleNamespace(
                id="forwarded-message-id",
                web_link="https://outlook.office365.com/owa/?ItemID=forwarded-message-id",
                sent_time="2026-09-02T08:30:00Z",
                html_body=(
                    "<div>From: Huajie Zhang &lt;huajiezhang@microsoft.com&gt;</div>"
                    "<div>Sent: September 2, 2026</div>"
                    "<div>To: Manager</div>"
                    "<div>Subject: Allowed message</div>"
                    "<p>Quarterly report details.</p>"
                ),
            )
        )
        context = SimpleNamespace(
            adapter=object(),
            activity=SimpleNamespace(
                from_property=SimpleNamespace(
                    id="HuajieZhang@activityprotocol66.onmicrosoft.com"
                ),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                ),
            )
        )

        with patch(
            "foundry_m365_autopilot.agent.send_proactive_message",
            new_callable=AsyncMock,
        ) as proactive_send:
            result = await agent._handle_forwarded_email_notification(
                notification,
                _FakeAuth(),
                "AGENTIC",
                context,
            )

        agent._invoke_responses_api.assert_awaited_once()
        summary_call = agent._invoke_responses_api.await_args.kwargs
        self.assertEqual(summary_call["mcp_server_labels"], ())
        self.assertFalse(summary_call["include_local_function_tools"])
        self.assertIn("in English", summary_call["instructions"])
        proactive_send.assert_awaited_once()
        self.assertEqual(proactive_send.await_args.args[2], "Matched monitored email")
        attachment = proactive_send.await_args.kwargs["attachments"][0]
        serialized = json.dumps(attachment, ensure_ascii=False)
        self.assertIn("Allowed message", serialized)
        self.assertIn("季度报告需要经理审阅。", serialized)
        self.assertIn("Find email in Outlook", serialized)
        self.assertIn("outlook.office.com/mail/search", serialized)
        self.assertNotIn("forwarded-message-id", serialized)
        self.assertEqual(result, "proactive_message_sent")

    async def test_forward_requires_saved_manager_conversation(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        agent._mail_monitor_store = _FakeMonitoringStore(
            {
                "version": "1.0",
                "enabled": True,
                "managerObjectId": "manager-object-id",
                "filter": {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "originalSender.address",
                            "operator": "equals",
                            "value": "huajiezhang@microsoft.com",
                        }
                    ],
                },
            }
        )
        agent._invoke_responses_api = AsyncMock(return_value="不应生成此摘要。")
        context = SimpleNamespace(
            activity=SimpleNamespace(
                from_property=SimpleNamespace(
                    id="HuajieZhang@activityprotocol66.onmicrosoft.com"
                ),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                ),
            )
        )

        result = await agent._handle_forwarded_email(
            raw_body=(
                "From: Huajie Zhang <huajiezhang@microsoft.com>\n"
                "Sent: September 2, 2026\n"
                "To: Manager <manager@contoso.com>\n"
                "Subject: Fallback message\n\nBody"
            ),
            message_id="fallback-message-id",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=context,
        )

        agent._invoke_responses_api.assert_not_awaited()
        self.assertEqual(result, "manager_conversation_unavailable")

    def test_builds_fixed_manager_notification_card(self) -> None:
        notification = build_manager_notification(
            {
                "sender": "alice@contoso.com",
                "subject": "Approval",
                "sentAt": "2026-09-02T08:30:00Z",
            },
            "这是一段超过五十个字符的摘要内容，用于验证代码无论模型返回多少文字都会执行固定长度截断，确保卡片布局稳定且满足产品要求。",
        )

        self.assertEqual(
            notification["contentType"],
            "application/vnd.microsoft.card.adaptive",
        )
        content = notification["content"]
        title = content["body"][0]
        self.assertEqual(title["text"], "Matched monitored email")
        self.assertEqual(title["size"], "Large")
        self.assertEqual(title["weight"], "Bolder")
        self.assertEqual(title["color"], "Attention")
        facts = content["body"][1]["facts"]
        self.assertEqual(
            [fact["title"] for fact in facts],
            ["Original sender", "Subject", "Sent time"],
        )
        self.assertEqual(len(content["body"][3]["text"]), 50)
        self.assertEqual(content["actions"][0]["type"], "Action.OpenUrl")
        search_url = content["actions"][0]["url"]
        self.assertIn("outlook.office.com/mail/search?q=", search_url)
        self.assertIn("from%3A%22alice%40contoso.com%22", search_url)
        self.assertIn("subject%3A%22Approval%22", search_url)

    def test_replaces_model_refusal_with_summary_fallback(self) -> None:
        self.assertEqual(
            normalize_mail_summary(
                "I'm sorry, but I cannot assist with that request."
            ),
            "Summary unavailable. Open the email for details.",
        )
        self.assertEqual(
            normalize_mail_summary("I can't help with that request."),
            "Summary unavailable. Open the email for details.",
        )

    def test_normalizes_numeric_forwarded_time_and_activity_fallback(self) -> None:
        parsed = parse_forwarded_email(
            "From: Alice <alice@contoso.com>\n"
            "Sent: Wednesday, 09/02/2026 8:30 AM (UTC-07:00)\n"
            "To: Manager <manager@contoso.com>\n"
            "Subject: Approval\n\nBody"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["sentAt"], "2026-09-02T15:30:00Z")
        self.assertEqual(
            normalize_forwarded_sent_at("2026-09-02T08:30:00Z"),
            "2026-09-02T08:30:00Z",
        )

    def test_accepts_successful_teams_mcp_call(self) -> None:
        FoundryDigitalWorkerAgent._require_successful_mcp_call(
            {
                "id": "response-id",
                "output": [
                    {
                        "type": "mcp_call",
                        "server_label": "mcp_TeamsServer",
                        "name": "SendChatMessage",
                        "output": "sent",
                        "error": None,
                    }
                ],
            },
            "mcp_TeamsServer",
        )

    def test_rejects_missing_teams_mcp_call(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "without calling required MCP server"):
            FoundryDigitalWorkerAgent._require_successful_mcp_call(
                {
                    "id": "response-id",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                        }
                    ],
                },
                "mcp_TeamsServer",
            )

    def test_rejects_failed_teams_mcp_call(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "MCP calls failed"):
            FoundryDigitalWorkerAgent._require_successful_mcp_call(
                {
                    "id": "response-id",
                    "output": [
                        {
                            "type": "mcp_call",
                            "server_label": "mcp_TeamsServer",
                            "name": "SendChatMessage",
                            "output": None,
                            "error": {"code": "forbidden", "message": "Denied"},
                        }
                    ],
                },
                "mcp_TeamsServer",
            )

    def test_rejects_unexpected_teams_mcp_approval_request(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unexpected approval"):
            FoundryDigitalWorkerAgent._require_successful_mcp_call(
                {
                    "id": "response-id",
                    "output": [
                        {
                            "id": "approval-id",
                            "type": "mcp_approval_request",
                            "server_label": "mcp_TeamsServer",
                            "name": "SendChatMessage",
                        }
                    ],
                },
                "mcp_TeamsServer",
            )

    def test_selects_mail_mcp_for_current_agent_user_mailbox_request(self) -> None:
        self.assertEqual(
            FoundryDigitalWorkerAgent._select_mcp_server_labels_for_turn(
                "Show my latest inbox messages."
            ),
            ("mcp_MailTools",),
        )

    def test_does_not_select_mail_mcp_for_delegated_mailbox_request(self) -> None:
        self.assertEqual(
            FoundryDigitalWorkerAgent._select_mcp_server_labels_for_turn(
                "Show the latest Inbox messages for owner@contoso.com."
            ),
            (),
        )

    def test_does_not_select_mcp_for_ordinary_chat(self) -> None:
        self.assertEqual(
            FoundryDigitalWorkerAgent._select_mcp_server_labels_for_turn(
                "Draft a concise project update."
            ),
            (),
        )

    def test_builds_activity_context_card_with_manager_section(self) -> None:
        activity = SimpleNamespace(
            channel_id="msteams",
            locale="en-US",
            service_url="https://service.example/tenant/conversation",
            channel_data={"tenant": {"id": "tenant-id"}},
            from_property=SimpleNamespace(
                name="Huajie Zhang",
                id="29:1234567890abcdefghijklmnopqrstuvwxyz",
                aad_object_id="manager-object-id",
            ),
            conversation=SimpleNamespace(
                id="19:abcdefghijklmnopqrstuvwxyz0123456789@thread.v2",
                conversation_type="personal",
            ),
            recipient=SimpleNamespace(
                tenant_id="tenant-id",
                agentic_app_id="agent-app-id-abcdefghijklmnopqrstuvwxyz",
                agentic_user_id="agent-user-id-abcdefghijklmnopqrstuvwxyz",
            ),
        )

        attachment = build_activity_context_attachment(
            activity,
            "session-id-email-1234567890",
            manager={
                "displayName": "Huajie Zhang",
                "userPrincipalName": "HuajieZhang@activityprotocol66.onmicrosoft.com",
                "mail": "HuajieZhang@activityprotocol66.onmicrosoft.com",
            },
        )
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertIn("Agent Manager", serialized)
        self.assertIn("HuajieZhang@activityprotocol66.onmicrosoft.com", serialized)
        self.assertIn("Only email forwarded by this Manager", serialized)
        self.assertIn("session-id-email-1234567890", serialized)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", serialized)
        sections = attachment["content"]["body"][2:]
        self.assertTrue(all(section["style"] == "emphasis" for section in sections))
        self.assertTrue(all(section["separator"] is True for section in sections))

    def test_builds_fixed_email_capabilities_card(self) -> None:
        attachment = build_capabilities_attachment()
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertIn("Agent User mailbox", serialized)
        self.assertIn("Delegated mailbox", serialized)
        self.assertIn("Forwarded-email monitoring", serialized)
        self.assertIn("Teams notifications", serialized)

    async def test_model_classifies_capabilities_without_tools(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "CAPABILITIES"})
        )

        intent = await agent.classify_user_intent("你好，请介绍一下你能做什么")

        self.assertEqual(intent, agent.CAPABILITIES_INTENT)
        request = agent._http_client.requests[0]["json"]
        self.assertNotIn("tools", request)
        self.assertEqual(request["input"], "你好，请介绍一下你能做什么")

    async def test_model_classification_failure_defaults_to_other(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"error": "unavailable"}, status_code=500)
        )

        intent = await agent.classify_user_intent("Send a status update")

        self.assertEqual(intent, agent.OTHER_INTENT)

    async def test_model_classifies_monitoring_status_without_tools(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "MONITORING_STATUS"})
        )

        intent = await agent.classify_user_intent("查看邮箱监控配置")

        self.assertEqual(intent, agent.MONITORING_STATUS_INTENT)
        request = agent._http_client.requests[0]["json"]
        self.assertNotIn("tools", request)
        self.assertEqual(request["input"], "查看邮箱监控配置")

    async def test_model_classifies_monitoring_configuration(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "CONFIGURE_MONITORING"})
        )

        intent = await agent.classify_user_intent("设置邮件监控，主题包含审批")

        self.assertEqual(intent, agent.CONFIGURE_MONITORING_FORM_INTENT)

    async def test_plain_config_request_uses_adaptive_card_intent(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "OPEN_MONITORING_FORM"})
        )

        intent = await agent.classify_user_intent("create email monitor config")

        self.assertEqual(intent, agent.CONFIGURE_MONITORING_FORM_INTENT)
        request = agent._http_client.requests[0]["json"]
        self.assertEqual(request["input"], "create email monitor config")
        self.assertIn("whether or not they already provided filter conditions", request["instructions"])

    async def test_plain_modify_request_uses_json_editor_intent(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "EDIT_MONITORING_JSON"})
        )

        intent = await agent.classify_user_intent("edit raw email monitoring JSON")

        self.assertEqual(intent, agent.EDIT_MONITORING_JSON_INTENT)

    async def test_plain_enable_uses_existing_monitoring_rule_intent(self) -> None:
        agent = self._responses_agent(
            _ResponsesResponse({"output_text": "ENABLE_MONITORING"})
        )

        intent = await agent.classify_user_intent("enable email monitor")

        self.assertEqual(intent, agent.ENABLE_MONITORING_INTENT)

    def test_builds_monitoring_configuration_card(self) -> None:
        attachment = build_monitoring_configuration_attachment(
            {
                "enabled": True,
                "filterDescription": "主题包含“important”",
                "sourceText": "监控标题包含 important 的邮件",
            }
        )
        serialized = json.dumps(attachment, ensure_ascii=False)

        self.assertIn("Email monitoring enabled", serialized)
        self.assertIn("主题包含", serialized)
        self.assertNotIn("<p>", serialized)

    def test_builds_monitoring_form_with_existing_values(self) -> None:
        attachment = build_monitoring_form_attachment(
            {
                "filter": {
                    "match": "any",
                    "conditions": [
                        {
                            "field": "subject",
                            "operator": "contains",
                            "value": "审批",
                        }
                    ],
                }
            }
        )
        content = attachment["content"]
        subject_input = next(
            item for item in content["body"] if item.get("id") == "subjectContains"
        )

        self.assertEqual(subject_input["value"], "审批")
        action = content["actions"][0]
        self.assertEqual(action["type"], "Action.Submit")
        self.assertEqual(action["data"]["monitoringAction"], CONFIGURE_FORM_VERB)
        self.assertEqual(action["data"]["msteams"]["type"], "messageBack")
        self.assertEqual(
            action["data"]["msteams"]["text"], CONFIGURE_FORM_SUBMIT_TEXT
        )
        self.assertEqual(
            action["data"]["msteams"]["value"]["monitoringAction"],
            CONFIGURE_FORM_VERB,
        )

    def test_builds_form_configuration_arguments(self) -> None:
        arguments = build_form_configuration_arguments(
            {
                "matchMode": "all",
                "senderAddress": "approvals@contoso.com",
                "subjectContains": "审批",
                "bodyContains": "",
                "importance": "high",
            }
        )

        self.assertEqual(arguments["filter"]["match"], "all")
        self.assertEqual(len(arguments["filter"]["conditions"]), 3)
        self.assertEqual(
            arguments["filter"]["conditions"][0]["value"],
            "approvals@contoso.com",
        )

    def test_form_configuration_requires_at_least_one_condition(self) -> None:
        with self.assertRaises(MailFilterValidationError):
            build_form_configuration_arguments(
                {
                    "matchMode": "all",
                    "senderAddress": "",
                    "subjectContains": "",
                    "bodyContains": "",
                    "importance": "",
                }
            )

    def test_builds_json_editor_and_ignores_identity_fields_on_submit(self) -> None:
        config = {
            "tenantId": "trusted-tenant",
            "managerObjectId": "trusted-manager",
            "sourceText": "Existing rule",
            "filter": {
                "match": "all",
                "conditions": [
                    {"field": "subject", "operator": "contains", "value": "审批"}
                ],
            },
        }
        attachment = build_monitoring_json_attachment(config)
        json_input = next(
            item for item in attachment["content"]["body"] if item.get("id") == "configJson"
        )
        arguments = build_json_configuration_arguments(
            {"configJson": json_input["value"]}
        )

        action = attachment["content"]["actions"][0]
        self.assertEqual(action["type"], "Action.Submit")
        self.assertEqual(action["data"]["monitoringAction"], EDIT_JSON_VERB)
        self.assertEqual(action["data"]["msteams"]["text"], EDIT_JSON_SUBMIT_TEXT)
        self.assertEqual(arguments["source_text"], "Existing rule")
        self.assertNotIn("tenantId", arguments)
        self.assertNotIn("managerObjectId", arguments)

    def test_json_editor_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(MailFilterValidationError, "valid JSON"):
            build_json_configuration_arguments({"configJson": "{not-json}"})

    def test_extracts_action_execute_payload(self) -> None:
        verb, data = get_execute_action(
            {
                "action": {
                    "type": "Action.Execute",
                    "verb": CONFIGURE_FORM_VERB,
                    "data": {"subjectContains": "Approval"},
                }
            }
        )

        self.assertEqual(verb, CONFIGURE_FORM_VERB)
        self.assertEqual(data["subjectContains"], "Approval")

    def test_extracts_action_submit_payload(self) -> None:
        verb, data = get_submit_action(
            {
                "monitoringAction": CONFIGURE_FORM_VERB,
                "subjectContains": "Approval",
            }
        )

        self.assertEqual(verb, CONFIGURE_FORM_VERB)
        self.assertEqual(data["subjectContains"], "Approval")

    def test_extracts_nested_message_back_payload(self) -> None:
        verb, data = get_submit_action(
            {
                "subjectContains": "Approval",
                "msteams": {
                    "value": {"monitoringAction": CONFIGURE_FORM_VERB}
                },
            }
        )

        self.assertEqual(verb, CONFIGURE_FORM_VERB)
        self.assertEqual(data["subjectContains"], "Approval")

    def test_builds_plain_text_monitoring_clarification_card(self) -> None:
        attachment = build_monitoring_clarification_attachment(
            "<p><b>请确认：</b></p><ul><li>是否区分大小写？</li></ul>"
        )
        serialized = json.dumps(attachment, ensure_ascii=False)

        self.assertIn("Complete your monitoring rule", serialized)
        self.assertIn("请确认", serialized)
        self.assertNotIn("<p>", serialized)
        self.assertNotIn("<li>", serialized)

    def test_builds_enabled_monitoring_status_card(self) -> None:
        attachment = build_monitoring_status_attachment(
            {
                "enabled": True,
                "currentManager": {
                    "displayName": "Huajie Zhang",
                    "userPrincipalName": "huajie@example.com",
                },
                "filterDescription": "主题包含“审批” 且 重要性等于“high”",
                "sourceText": "监听审批邮件",
                "updatedAt": "2026-09-11T04:00:00Z",
                "config": {
                    "enabled": True,
                    "filter": {
                        "match": "all",
                        "conditions": [
                            {
                                "field": "subject",
                                "operator": "contains",
                                "value": "审批",
                            }
                        ],
                    },
                },
            }
        )
        serialized = json.dumps(attachment, ensure_ascii=False)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertIn("Email monitoring", serialized)
        self.assertIn("Huajie Zhang", serialized)
        self.assertIn("主题包含", serialized)
        config_section = next(
            item
            for item in attachment["content"]["body"]
            if item.get("items", [{}])[0].get("text") == "Config"
        )
        toggle_action = config_section["items"][1]["actions"][0]
        raw_json = config_section["items"][2]
        self.assertEqual(toggle_action["type"], "Action.ToggleVisibility")
        self.assertEqual(
            toggle_action["targetElements"], ["monitoring-config-json"]
        )
        self.assertFalse(raw_json["isVisible"])
        self.assertEqual(raw_json["fontType"], "Monospace")
        self.assertIn('"value": "审批"', raw_json["text"])
        self.assertNotIn("<p>", serialized)

    def test_builds_disabled_monitoring_status_card(self) -> None:
        attachment = build_monitoring_status_attachment(
            {
                "enabled": False,
                "currentManager": {"displayName": "Huajie Zhang"},
            }
        )
        serialized = json.dumps(attachment)

        self.assertIn('"text": "OFF"', serialized)
        self.assertNotIn("Active rule", serialized)

    async def test_activity_context_card_resolves_current_manager(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        context = SimpleNamespace(
            activity=SimpleNamespace(
                channel_id="msteams",
                locale="en-US",
                from_property=SimpleNamespace(
                    name="Huajie Zhang",
                    id="manager-object-id",
                    aad_object_id="manager-object-id",
                ),
                conversation=SimpleNamespace(id="conversation-id"),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                    agentic_app_id="agent-app-id",
                ),
            )
        )

        attachment = await agent.build_activity_context_attachment(
            _FakeAuth(),
            "AGENTIC",
            context,
        )
        serialized = json.dumps(attachment)

        self.assertIn("Agent Manager", serialized)
        self.assertIn("Huajie Zhang", serialized)
        self.assertIn("HuajieZhang@activityprotocol66.onmicrosoft.com", serialized)

    async def test_email_message_activity_runs_forwarded_email_workflow(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        captured: dict = {}

        async def handle_forwarded_email(**kwargs):
            captured.update(kwargs)

        agent._handle_forwarded_email = handle_forwarded_email
        context = SimpleNamespace(
            activity=SimpleNamespace(
                id="activity-message-id",
                channel_id="agents",
                entities=[{"type": "productInfo", "id": "email"}],
                from_property=SimpleNamespace(
                    id="HuajieZhang@activityprotocol66.onmicrosoft.com",
                    name="Huajie Zhang",
                ),
            )
        )

        result = await agent.process_user_message(
            "From: Huajie Zhang <huajiezhang@microsoft.com>\n"
            "Sent: Thursday, September 3, 2026\n"
            "To: Agent <agent@contoso.com>\n"
            "Subject: Email test\n\nBody",
            _FakeAuth(),
            "AGENTIC",
            context,
        )

        self.assertEqual(result, "")
        self.assertEqual(captured["message_id"], "activity-message-id")
        self.assertIn("huajiezhang@microsoft.com", captured["raw_body"])

    async def test_help_request_returns_capabilities_without_model_call(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        invoked = False

        async def invoke_responses_api(**kwargs):
            nonlocal invoked
            invoked = True

        agent._invoke_responses_api = invoke_responses_api
        context = SimpleNamespace(
            activity=SimpleNamespace(
                channel_id="msteams",
                entities=[],
                from_property=SimpleNamespace(name="Manager", id="manager-id"),
            )
        )

        result = await agent.process_user_message(
            "你能做什么？",
            _FakeAuth(),
            "AGENTIC",
            context,
        )

        self.assertFalse(invoked)
        self.assertIn("设置的条件", result)
        self.assertIn("取消邮件监听", result)

    async def test_nonmatching_original_sender_is_ignored_before_model_call(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        agent._mail_monitor_store = _FakeMonitoringStore(
            {
                "version": "1.0",
                "enabled": True,
                "managerObjectId": "manager-object-id",
                "filter": {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "originalSender.address",
                            "operator": "equals",
                            "value": "huajiezhang@microsoft.com",
                        }
                    ],
                },
            }
        )
        invoked = False

        async def invoke_responses_api(**kwargs):
            nonlocal invoked
            invoked = True

        agent._invoke_responses_api = invoke_responses_api
        notification = SimpleNamespace(
            email=SimpleNamespace(
                id="message-id",
                html_body=(
                    "<div>From: Attacker &lt;attacker@example.com&gt;</div>"
                    "<div>Sent: September 2, 2026</div>"
                    "<div>To: Manager</div>"
                    "<div>Subject: Ignore me</div>"
                    "<p>Untrusted body.</p>"
                ),
            )
        )
        context = SimpleNamespace(
            activity=SimpleNamespace(
                from_property=SimpleNamespace(
                    id="HuajieZhang@activityprotocol66.onmicrosoft.com"
                ),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                ),
            )
        )

        await agent._handle_forwarded_email_notification(
            notification,
            _FakeAuth(),
            "AGENTIC",
            context,
        )

        self.assertFalse(invoked)

    async def test_monitoring_is_disabled_by_default(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        agent._mail_monitor_store = _FakeMonitoringStore()
        invoked = False

        async def invoke_responses_api(**kwargs):
            nonlocal invoked
            invoked = True

        agent._invoke_responses_api = invoke_responses_api
        context = SimpleNamespace(
            activity=SimpleNamespace(
                from_property=SimpleNamespace(
                    id="HuajieZhang@activityprotocol66.onmicrosoft.com"
                ),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                ),
            )
        )

        await agent._handle_forwarded_email(
            raw_body=(
                "From: Huajie Zhang <huajiezhang@microsoft.com>\n"
                "Sent: Thursday, September 3, 2026 2:01:08 PM (UTC+08:00)\n"
                "To: Manager <manager@contoso.com>\n"
                "Subject: Should be ignored\n\nBody"
            ),
            message_id="message-id",
            auth=_FakeAuth(),
            auth_handler_name="AGENTIC",
            context=context,
        )

        self.assertFalse(invoked)

    async def test_manager_can_configure_query_and_disable_monitoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMailMonitoringStore(Path(directory))
            context = SimpleNamespace(
                activity=SimpleNamespace(
                    channel_id="msteams",
                    from_property=SimpleNamespace(
                        id="teams-user-id",
                        aad_object_id="manager-object-id",
                    ),
                    recipient=SimpleNamespace(
                        tenant_id="tenant-id",
                        agentic_user_id="agent-user-id",
                    ),
                )
            )
            runtime = _tool_runtime(
                auth=_FakeAuth(),
                context=context,
                http_client=_ManagerHttpClient(),
                store=store,
            )
            invalid_result = await dispatch(
                "configure_mail_monitoring",
                {"source_text": "", "filter": {}},
                runtime,
            )
            configure_result = await dispatch(
                "configure_mail_monitoring",
                {
                    "source_text": "监听主题包含审批的高重要性邮件",
                    "filter": {
                        "match": "all",
                        "conditions": [
                            {
                                "field": "subject",
                                "operator": "contains",
                                "value": "审批",
                            },
                            {
                                "field": "importance",
                                "operator": "equals",
                                "value": "high",
                            },
                        ],
                    },
                },
                runtime,
            )
            status_result = await dispatch(
                "get_mail_monitoring_status",
                {},
                runtime,
            )
            disable_result = await dispatch(
                "disable_mail_monitoring",
                {},
                runtime,
            )
            enable_result = await dispatch(
                "enable_mail_monitoring",
                {},
                runtime,
            )

            self.assertEqual(
                invalid_result["error"]["code"], "configuration_failed"
            )
            self.assertTrue(configure_result["enabled"])
            self.assertIn("主题包含", configure_result["filterDescription"])
            self.assertTrue(status_result["enabled"])
            self.assertEqual(
                status_result["currentManager"]["userPrincipalName"],
                "HuajieZhang@activityprotocol66.onmicrosoft.com",
            )
            self.assertIn("current Manager", status_result["forwardedEmailRule"])
            self.assertEqual(
                status_result["config"]["filter"]["conditions"][0],
                {
                    "field": "subject",
                    "operator": "contains",
                    "value": "审批",
                },
            )
            self.assertFalse(disable_result["enabled"])
            self.assertIn("forwarding rule", disable_result["forwardingRuleNotice"])
            self.assertTrue(enable_result["enabled"])
            self.assertIn("主题包含", enable_result["filterDescription"])
            saved_config = await store.get("tenant-id", "agent-user-id")
            self.assertTrue(saved_config["enabled"])
            self.assertEqual(
                saved_config["filter"]["conditions"][0]["value"], "审批"
            )

    async def test_enable_monitoring_requires_saved_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = SimpleNamespace(
                activity=SimpleNamespace(
                    channel_id="msteams",
                    from_property=SimpleNamespace(
                        id="teams-user-id",
                        aad_object_id="manager-object-id",
                    ),
                    recipient=SimpleNamespace(
                        tenant_id="tenant-id",
                        agentic_user_id="agent-user-id",
                    ),
                )
            )
            result = await dispatch(
                "enable_mail_monitoring",
                {},
                _tool_runtime(
                    auth=_FakeAuth(),
                    context=context,
                    http_client=_ManagerHttpClient(),
                    store=LocalFileMailMonitoringStore(Path(directory)),
                ),
            )

            self.assertEqual(result["status"], "configuration_required")
            self.assertFalse(result["enabled"])

    async def test_non_manager_cannot_configure_monitoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = SimpleNamespace(
                activity=SimpleNamespace(
                    channel_id="msteams",
                    from_property=SimpleNamespace(aad_object_id="someone-else"),
                    recipient=SimpleNamespace(
                        tenant_id="tenant-id",
                        agentic_user_id="agent-user-id",
                    ),
                )
            )

            result = await dispatch(
                "get_mail_monitoring_status",
                {},
                _tool_runtime(
                    auth=_FakeAuth(),
                    context=context,
                    http_client=_ManagerHttpClient(),
                    store=LocalFileMailMonitoringStore(Path(directory)),
                ),
            )

            self.assertEqual(result["error"]["code"], "not_authorized")

    async def test_invalid_registry_arguments_preserve_error_shape(self) -> None:
        runtime = _tool_runtime(
            auth=_FakeAuth(),
            context=object(),
            http_client=_FakeHttpClient(),
        )

        malformed = await dispatch(
            "read_delegated_mailbox_inbox", "{not-json", runtime
        )
        invalid_mailbox = await dispatch(
            "read_delegated_mailbox_inbox",
            {"user_principal_name": "not-a-upn", "top": 5},
            runtime,
        )

        self.assertEqual(malformed["error"]["code"], "invalid_arguments")
        self.assertEqual(invalid_mailbox["error"]["code"], "invalid_arguments")

    def test_normalizes_and_matches_supported_filter_fields(self) -> None:
        expression = {
            "match": "all",
            "conditions": [
                {
                    "field": "originalSender.address",
                    "operator": "in",
                    "value": ["ALICE@CONTOSO.COM", "bob@contoso.com"],
                },
                {
                    "field": "subject",
                    "operator": "containsAny",
                    "value": ["审批", "urgent"],
                },
                {
                    "field": "body.text",
                    "operator": "contains",
                    "value": "Friday",
                },
                {
                    "field": "sentAt",
                    "operator": "after",
                    "value": "2026-09-01T00:00:00Z",
                },
                {
                    "field": "importance",
                    "operator": "equals",
                    "value": "HIGH",
                },
            ],
        }
        normalized = normalize_filter(expression)
        matched = matches_filter(
            normalized,
            {
                "originalSender": {"address": "alice@contoso.com"},
                "subject": "合同审批",
                "body": {"text": "Please complete this by Friday."},
                "sentAt": "2026-09-03T06:01:08Z",
                "importance": "high",
            },
        )

        self.assertTrue(matched)
        self.assertEqual(
            normalized["conditions"][0]["value"][0], "alice@contoso.com"
        )
        self.assertIn("重要性等于", describe_filter(normalized))

    def test_normalizes_single_item_list_for_scalar_text_operator(self) -> None:
        expression = {
            "match": "all",
            "conditions": [
                {
                    "field": "subject",
                    "operator": "contains",
                    "value": ["important"],
                },
                {
                    "field": "originalSender.address",
                    "operator": "equals",
                    "value": "huajiezhang@microsoft.com",
                },
            ],
        }

        normalized = normalize_filter(expression)

        self.assertEqual(normalized["conditions"][0]["value"], "important")
        self.assertTrue(
            matches_filter(
                normalized,
                {
                    "originalSender": {
                        "address": "huajiezhang@microsoft.com"
                    },
                    "subject": "important: test email 0914",
                },
            )
        )

        persisted_expression = {
            **expression,
            "conditions": [
                {**expression["conditions"][0], "value": "['important']"},
                expression["conditions"][1],
            ],
        }
        self.assertTrue(
            matches_filter(
                persisted_expression,
                {
                    "originalSender": {
                        "address": "huajiezhang@microsoft.com"
                    },
                    "subject": "important: test email 0914",
                },
            )
        )

    async def test_local_store_isolates_agent_users(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileMailMonitoringStore(Path(directory))
            await store.save(
                "tenant-id",
                "agent-user-one",
                {"id": "manager-object-id", "userPrincipalName": "manager@contoso.com"},
                "监听审批邮件",
                {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "subject",
                            "operator": "contains",
                            "value": "审批",
                        }
                    ],
                },
            )

            self.assertIsNotNone(await store.get("tenant-id", "agent-user-one"))
            self.assertIsNone(await store.get("tenant-id", "agent-user-two"))

    async def test_blob_store_shares_configuration_across_sessions(self) -> None:
        container = _FakeContainerClient()
        teams_session_store = AzureBlobMailMonitoringStore(
            "", "", None, container_client=container
        )
        email_session_store = AzureBlobMailMonitoringStore(
            "", "", None, container_client=container
        )

        await teams_session_store.save(
            "tenant-id",
            "agent-user-id",
            {"id": "manager-object-id", "mail": "manager@contoso.com"},
            "监听标题包含 important 的邮件",
            {
                "match": "all",
                "conditions": [
                    {
                        "field": "subject",
                        "operator": "contains",
                        "value": "important",
                    }
                ],
            },
        )

        configured = await email_session_store.get("tenant-id", "agent-user-id")
        self.assertTrue(configured["enabled"])
        self.assertEqual(configured["managerObjectId"], "manager-object-id")

        await email_session_store.disable("tenant-id", "agent-user-id")
        disabled = await teams_session_store.get("tenant-id", "agent-user-id")
        self.assertFalse(disabled["enabled"])

    async def test_blob_store_shares_manager_conversation_across_sessions(self) -> None:
        container = _FakeContainerClient()
        teams_session_store = AzureBlobMailMonitoringStore(
            "", "", None, container_client=container
        )
        email_session_store = AzureBlobMailMonitoringStore(
            "", "", None, container_client=container
        )
        conversation = {
            "version": "1.0",
            "conversation": {"claims": {}, "conversation_reference": {}},
        }

        await teams_session_store.save_manager_conversation(
            "tenant-id", "agent-user-id", conversation
        )

        self.assertEqual(
            await email_session_store.get_manager_conversation(
                "tenant-id", "agent-user-id"
            ),
            conversation,
        )

    async def test_manager_teams_turn_saves_proactive_conversation(self) -> None:
        agent = object.__new__(FoundryDigitalWorkerAgent)
        agent._http_client = _ManagerHttpClient()
        agent._manager_cache = {}
        agent._mail_monitor_store = _FakeMonitoringStore()
        context = SimpleNamespace(
            activity=SimpleNamespace(
                from_property=SimpleNamespace(
                    id="8:orgid:manager-object-id",
                    aad_object_id="manager-object-id",
                ),
                recipient=SimpleNamespace(
                    tenant_id="tenant-id",
                    agentic_user_id="agent-user-id",
                ),
            )
        )
        conversation = {"version": "1.0", "conversation": {}}

        with patch(
            "foundry_m365_autopilot.agent.build_conversation_record",
            return_value=conversation,
        ):
            await agent._remember_manager_conversation(
                _FakeAuth(), "AGENTIC", context
            )

        self.assertEqual(agent._mail_monitor_store.conversation, conversation)

    async def test_proactive_message_continues_saved_conversation(self) -> None:
        class _Adapter:
            def __init__(self) -> None:
                self.activity = None

            async def continue_conversation_with_claims(
                self, claims, continuation, callback
            ):
                sent = []

                async def send_activity(activity):
                    sent.append(activity)

                await callback(SimpleNamespace(send_activity=send_activity))
                self.activity = sent[0]

        adapter = _Adapter()
        record = {
            "version": "1.0",
            "conversation": {
                "claims": {"aud": "agent-audience", "tid": "tenant-id"},
                "conversation_reference": {
                    "serviceUrl": "https://smba.trafficmanager.net/amer/",
                    "channelId": "msteams",
                    "conversation": {"id": "conversation-id"},
                    "bot": {"id": "agent-id"},
                    "user": {"id": "manager-id"},
                },
            },
        }

        await send_proactive_message(adapter, record, "mail summary")

        self.assertEqual(adapter.activity.text, "mail summary")
        self.assertEqual(adapter.activity.type, "message")

        attachment = build_manager_notification(
            {"sender": "alice@contoso.com", "subject": "Approval"},
            "请审阅审批邮件。",
        )
        await send_proactive_message(
            adapter,
            record,
            "Matched monitored email",
            attachments=[attachment],
        )

        sent_attachment = adapter.activity.attachments[0]
        self.assertEqual(
            sent_attachment.content_type,
            "application/vnd.microsoft.card.adaptive",
        )
        self.assertEqual(sent_attachment.content, attachment["content"])

    def test_rejects_unsupported_filter_field(self) -> None:
        with self.assertRaises(MailFilterValidationError):
            normalize_filter(
                {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "attachments.name",
                            "operator": "contains",
                            "value": "secret.pdf",
                        }
                    ],
                }
            )

    def test_parses_forwarded_sent_time_for_filtering(self) -> None:
        forwarded = parse_forwarded_email(
            "From: Alice <alice@contoso.com>\n"
            "Sent: Thursday, September 3, 2026 2:01:08 PM (UTC+08:00)\n"
            "To: Manager <manager@contoso.com>\n"
            "Subject: Approval\n\nBody"
        )

        self.assertEqual(forwarded["sentAt"], "2026-09-03T06:01:08Z")


if __name__ == "__main__":
    unittest.main()