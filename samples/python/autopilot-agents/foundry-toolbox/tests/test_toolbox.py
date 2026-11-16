"""Offline integration tests using the real Agent Framework and Activity SDKs."""

import asyncio
import json
import os
import time
from copy import deepcopy
from io import BytesIO, TextIOWrapper
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import httpx2
import yaml
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from azure.ai.agentserver.core.platform_headers import (
    FOUNDRY_CALL_ID,
    SESSION_ID,
    USER_ID,
)
from azure.ai.projects.models import MCPToolboxTool, WebSearchToolboxTool
from azure.core.credentials import AccessToken
from microsoft_agents.hosting.core import RestChannelServiceClientFactory, TurnContext

from agent.app import build_app
from agent.toolbox import LEARN_TOOLS, WEB_SEARCH_TOOL, Settings, answer, main


PROJECT = "https://example.services.ai.azure.com/api/projects/sample"
ENDPOINT = f"{PROJECT}/toolboxes/public-docs/versions/1/mcp?api-version=v1"
ENV = {
    "FOUNDRY_PROJECT_ENDPOINT": PROJECT,
    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-model",
    "TOOLBOX_ENDPOINT": ENDPOINT,
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
}
SETTINGS = Settings(PROJECT, "test-model", ENDPOINT)
REPLY = "See [Microsoft Learn](https://learn.microsoft.com/azure/foundry/)."
WEB_SOURCE = "https://learn.microsoft.com/azure/foundry/agents/concepts/toolbox-overview"
WEB_REPLY = f"Public web search: [Foundry Toolbox overview]({WEB_SOURCE})."
ACTIVITY = {
    "type": "message",
    "id": "test-activity",
    "channelId": "msteams",
    "serviceUrl": "https://smba.trafficmanager.net/teams/",
    "from": {"id": "test-user"},
    "recipient": {"id": "test-agent", "name": "Docs"},
    "conversation": {"id": "test-conversation", "conversationType": "personal"},
    "text": "Find documentation on Foundry Toolboxes.",
}
TOOL_ARGUMENTS = {
    "learn.microsoft_docs_search": {"query": "Foundry Toolboxes"},
    "learn.microsoft_docs_fetch": {"url": "https://learn.microsoft.com/azure/foundry/"},
    "learn.microsoft_code_sample_search": {"query": "Azure Identity", "language": "python"},
    WEB_SEARCH_TOOL: {"search_query": "Recent public Microsoft Foundry announcements"},
}


class OfflineCredential:
    token = "offline-test-token"

    def __init__(self):
        self.scopes = []
        self.closed = False

    async def get_token(self, *scopes, **_kwargs):
        self.scopes.append(scopes)
        return AccessToken(self.token, int(time.time()) + 3600)

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        await self.close()


class OfflineServices:
    """Answer MCP and Responses requests without replacing their client implementations."""

    def __init__(self):
        self.requests = []
        self.approval = "never"
        self.empty_tools = False
        self.fail_initialize = False
        self.fail_call = False
        self.empty_reply = False
        self.sources = {"learn", WEB_SEARCH_TOOL}
        self.extra_tool: str | None = None
        self.tool_separator = "."
        self.tool_plan = ["learn.microsoft_docs_search"]
        self.web_type = "web_search"
        self.web_approval = None
        self.web_schema = {
            "type": "object",
            "properties": {"search_query": {"type": "string"}},
            "required": ["search_query"],
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        }

    def wire_name(self, name):
        return name.replace(".", self.tool_separator, 1)

    def tool_definitions(self):
        if self.empty_tools:
            return []
        tools = []
        for name, arguments in TOOL_ARGUMENTS.items():
            if name.split(".", 1)[0] not in self.sources:
                continue
            native = name == WEB_SEARCH_TOOL
            configuration = (
                {"type": self.web_type, "name": WEB_SEARCH_TOOL}
                if native
                else {"type": "mcp", "require_approval": self.approval}
            )
            if native and self.web_approval is not None:
                configuration["require_approval"] = self.web_approval
            tools.append(
                {
                    "name": self.wire_name(name),
                    "description": f"Read public documentation with {name}.",
                    "inputSchema": deepcopy(self.web_schema) if native else {
                        "type": "object",
                        "properties": {
                            key: {"type": "string"} for key in arguments
                        },
                        "required": [
                            key for key in arguments if key != "language"
                        ],
                    },
                    "_meta": {
                        "tool_configuration": configuration
                    },
                }
            )
        if self.extra_tool:
            tools.append(
                {
                    "name": self.extra_tool,
                    "inputSchema": {"type": "object", "properties": {}},
                }
            )
        return tools

    async def handle_mcp(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request, body))
        if request.method != "POST":
            return httpx.Response(405)
        method = body["method"]
        if method.startswith("notifications/"):
            return httpx.Response(202)
        if method == "initialize":
            if self.fail_initialize:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {
                            "code": -32603,
                            "message": "Offline initialization failure",
                        },
                    },
                )
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "offline-foundry-toolbox", "version": "1.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.tool_definitions()}
        elif method == "tools/call":
            name = body["params"]["name"]
            assert name in {self.wire_name(tool) for tool in TOOL_ARGUMENTS}, name
            if name == WEB_SEARCH_TOOL and not self.fail_call:
                result = {
                    "content": [
                        {
                            "type": "resource",
                            "resource": {
                                "uri": "about:web-search-answer",
                                "mimeType": "text/plain",
                                "text": WEB_REPLY,
                            },
                            "annotations": {"audience": ["assistant"]},
                            "_meta": {
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": WEB_SOURCE,
                                        "title": "Foundry Toolbox overview",
                                        "start_index": WEB_REPLY.index("["),
                                        "end_index": len(WEB_REPLY) - 1,
                                    }
                                ]
                            },
                        }
                    ],
                    "_meta": {
                        "tool_configuration": {
                            "type": "web_search",
                            "name": WEB_SEARCH_TOOL,
                        }
                    },
                    "isError": False,
                }
            else:
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": "Offline tool failure" if self.fail_call else REPLY,
                        }
                    ],
                    "isError": self.fail_call,
                }
        else:
            raise AssertionError(f"Unexpected MCP method: {method}")
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}
        )

    async def handle_model(self, request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(0)
        body = json.loads(request.content)
        self.requests.append((request, body))
        assert request.url.path.endswith("/responses"), str(request.url)
        assert body["model"] == "test-model"
        assert body["store"] is False
        completed = sum(
            item.get("type") == "function_call_output" for item in body["input"]
        )
        if completed < len(self.tool_plan):
            name = self.tool_plan[completed]
            wire_name = self.wire_name(name)
            assert wire_name in {tool["name"] for tool in body["tools"]}, wire_name
            output = [
                {
                    "type": "function_call",
                    "id": f"fc-test-{completed}",
                    "call_id": f"call-test-{completed}",
                    "name": wire_name,
                    "arguments": json.dumps(TOOL_ARGUMENTS[name]),
                    "status": "completed",
                }
            ]
        else:
            output = [
                {
                    "type": "message",
                    "id": "msg-test",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": ""
                            if self.empty_reply
                            else (
                                WEB_REPLY
                                if self.tool_plan[-1] == WEB_SEARCH_TOOL
                                else REPLY
                            ),
                            "annotations": [],
                        }
                    ],
                }
            ]
        return httpx2.Response(
            200,
            json={
                "id": f"resp-test-{completed}",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "test-model",
                "output": output,
            },
        )

    def mcp_requests(self):
        return [
            (request, body)
            for request, body in self.requests
            if "/toolboxes/" in request.url.path
        ]

    def tool_calls(self):
        return [
            (request, body)
            for request, body in self.mcp_requests()
            if body.get("method") == "tools/call"
        ]

    def model_requests(self):
        return [
            (request, body)
            for request, body in self.requests
            if request.url.path.endswith("/responses")
        ]


class SettingsTests(TestCase):
    def test_toolbox_definition_matches_learn_and_native_web_search(self):
        definition = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "toolbox.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(definition["name"], "public-docs")
        self.assertEqual(len(definition["tools"]), 2)
        tools = {tool["type"]: tool for tool in definition["tools"]}
        self.assertEqual(set(tools), {"mcp", "web_search"})
        learn, web = tools["mcp"], tools["web_search"]
        self.assertEqual(learn["server_label"], "learn")
        self.assertEqual(learn["server_url"], "https://learn.microsoft.com/api/mcp")
        self.assertEqual(
            {f"learn.{name}" for name in learn["allowed_tools"]},
            LEARN_TOOLS,
        )
        self.assertEqual(learn["require_approval"], "never")
        self.assertEqual(MCPToolboxTool(**learn).as_dict(), learn)
        self.assertEqual(web["name"], WEB_SEARCH_TOOL)
        self.assertEqual(WebSearchToolboxTool(**web).as_dict(), web)
        self.assertNotIn("custom_search_configuration", web)
        self.assertNotIn("server_url", web)
        self.assertNotIn("server_label", web)
        for tool in tools.values():
            self.assertNotIn("project_connection_id", tool)
            self.assertNotIn("headers", tool)

    def test_deployment_requires_no_downstream_auth_configuration(self):
        manifest = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "azure.yaml").read_text(
                encoding="utf-8"
            )
        )
        service = manifest["services"]["foundry-toolbox-autopilot"]
        self.assertNotIn("optionalPermissionScopes", service["activity"]["publish"])
        self.assertFalse(
            any("USERAUTHORIZATION" in name for name in service["env"])
        )
        self.assertNotIn("azure.ai.connections", manifest["requiredVersions"]["extensions"])
        self.assertEqual(service["codeConfiguration"]["runtime"], "python_3_13")

    def test_valid_consumer_and_versioned_endpoints(self):
        for endpoint in (ENDPOINT, ENDPOINT.replace("/versions/1", "")):
            with patch.dict(os.environ, {**ENV, "TOOLBOX_ENDPOINT": endpoint}, clear=True):
                self.assertEqual(Settings.from_env().toolbox_endpoint, endpoint)

    def test_missing_and_blank_settings_fail_explicitly(self):
        for key in (
            "FOUNDRY_PROJECT_ENDPOINT",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME",
            "TOOLBOX_ENDPOINT",
        ):
            for value in ("", "   "):
                with patch.dict(os.environ, {**ENV, key: value}, clear=True):
                    with self.assertRaisesRegex(ValueError, key):
                        Settings.from_env()

    def test_unrelated_or_malformed_toolbox_endpoints_are_rejected(self):
        endpoints = (
            ENDPOINT.replace("https:", "http:"),
            ENDPOINT.replace("example.services.ai.azure.com", "unrelated.example.com"),
            ENDPOINT.replace("/projects/sample/", "/projects/other/"),
            ENDPOINT.replace("/mcp?api-version=v1", "/mcp"),
            ENDPOINT.replace("api-version=v1", "api-version=v2"),
            ENDPOINT + "#fragment",
        )
        for endpoint in endpoints:
            with patch.dict(os.environ, {**ENV, "TOOLBOX_ENDPOINT": endpoint}, clear=True):
                with self.assertRaisesRegex(ValueError, "HTTPS Foundry toolbox"):
                    Settings.from_env()


class CliTests(TestCase):
    def test_cli_prints_unicode_search_answers_when_stdout_uses_windows_encoding(self):
        message = "Search the public web."
        response = "Foundry\u202fToolbox \u2014 sources \U0001f50e"
        output = BytesIO()
        with (
            TextIOWrapper(output, encoding="cp1252") as stream,
            patch.dict(os.environ, ENV, clear=True),
            patch("sys.argv", ["agent.toolbox", message]),
            patch("sys.stdout", stream),
            patch("agent.toolbox.logging.basicConfig"),
            patch("agent.toolbox.answer", new_callable=AsyncMock) as run,
        ):
            run.return_value = response
            main()
            stream.flush()
            self.assertEqual(output.getvalue().decode("utf-8"), response + os.linesep)
            run.assert_awaited_once_with(SETTINGS, message)


class _OfflineTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = OfflineServices()
        self.credentials = []
        self.clients = []
        self.toolboxes = []
        self.toolbox_transports = []
        self.project_closes = []
        self.contexts = []
        self.model_credentials = []
        self.toolbox_credentials = []

        def credential_factory(*_args, **_kwargs):
            credential = OfflineCredential()
            self.credentials.append(credential)
            return credential

        def client_factory(**kwargs):
            self.model_credentials.append(kwargs["credential"])
            client = FoundryChatClient(**kwargs)
            client.client._client._transport = httpx2.MockTransport(
                self.services.handle_model
            )
            client.client._client._mounts.clear()
            close = AsyncMock(wraps=client.project_client.close)
            client.project_client.close = close
            self.project_closes.append(close)
            self.clients.append(client)
            return client

        def toolbox_factory(credential, **kwargs):
            self.toolbox_credentials.append(credential)
            context = get_request_context()
            self.contexts.append((context.call_id, context.session_id, context.user_id))
            toolbox = FoundryToolbox(credential, **kwargs)
            assert toolbox._httpx_client is not None
            toolbox._httpx_client._transport = httpx.MockTransport(self.services.handle_mcp)
            toolbox._httpx_client._mounts.clear()
            self.toolbox_transports.append(toolbox._httpx_client)
            self.toolboxes.append(toolbox)
            return toolbox

        for patcher in (
            patch.dict(os.environ, ENV, clear=True),
            patch("agent.toolbox.AzureCliCredential", side_effect=credential_factory),
            patch("agent.toolbox.ManagedIdentityCredential", side_effect=credential_factory),
            patch("agent.toolbox.FoundryChatClient", side_effect=client_factory),
            patch("agent.toolbox.FoundryToolbox", side_effect=toolbox_factory),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_resources_closed(self):
        self.assertTrue(all(credential.closed for credential in self.credentials))
        self.assertTrue(all(client.client.is_closed for client in self.clients))
        self.assertTrue(all(transport.is_closed for transport in self.toolbox_transports))
        for close in self.project_closes:
            close.assert_awaited_once()

    def assert_tool_call(self, name, call_index=0):
        request, body = self.services.tool_calls()[call_index]
        self.assertEqual(str(request.url), ENDPOINT)
        self.assertEqual(body["params"]["name"], self.services.wire_name(name))
        self.assertEqual(body["params"]["arguments"], TOOL_ARGUMENTS[name])


class ToolboxTests(_OfflineTestCase):
    async def test_real_framework_discovers_calls_tool_and_returns_grounded_reply(self):
        self.assertEqual(await answer(SETTINGS, "Find Foundry documentation."), REPLY)
        self.assertEqual(len(self.services.tool_calls()), 1)
        self.assert_tool_call("learn.microsoft_docs_search")
        self.assertEqual(len(self.services.model_requests()), 2)
        self.assertTrue(
            any(
                item.get("type") == "function_call_output"
                and "Microsoft Learn" in item["output"]
                for item in self.services.model_requests()[1][1]["input"]
            )
        )
        for request, _ in self.services.mcp_requests():
            self.assertEqual(request.headers["Authorization"], f"Bearer {OfflineCredential.token}")
            self.assertIn("Toolboxes=V1Preview", request.headers["Foundry-Features"])
        self.assertIn(("https://ai.azure.com/.default",), self.credentials[0].scopes)
        self.assertIs(self.model_credentials[0], self.toolbox_credentials[0])
        self.assert_resources_closed()

    async def test_all_four_tools_execute_with_exact_wire_names_and_arguments(self):
        for separator in (".", "___"):
            self.services.tool_separator = separator
            for name in sorted(TOOL_ARGUMENTS):
                with self.subTest(separator=separator, tool=name):
                    self.services.requests.clear()
                    self.services.tool_plan = [name]
                    expected = WEB_REPLY if name == WEB_SEARCH_TOOL else REPLY
                    self.assertEqual(await answer(SETTINGS, "Read public docs."), expected)
                    self.assert_tool_call(name)
                    self.assertEqual(
                        set(self.toolboxes[-1].allowed_tools),
                        {self.services.wire_name(tool) for tool in TOOL_ARGUMENTS},
                    )
                    for _, body in self.services.model_requests():
                        self.assertEqual(
                            {tool["name"] for tool in body["tools"]},
                            {self.services.wire_name(tool) for tool in TOOL_ARGUMENTS},
                        )
                    if name == WEB_SEARCH_TOOL:
                        outputs = [
                            item["output"]
                            for item in self.services.model_requests()[1][1]["input"]
                            if item.get("type") == "function_call_output"
                        ]
                        self.assertTrue(any(WEB_REPLY in output for output in outputs))
                        self.assertTrue(any(WEB_SOURCE in output for output in outputs))
        self.assert_resources_closed()

    async def test_both_sources_execute_in_one_model_loop_and_mcp_session(self):
        self.services.tool_plan = [
            "learn.microsoft_docs_search",
            WEB_SEARCH_TOOL,
        ]
        self.assertEqual(await answer(SETTINGS, "Combine both public sources."), WEB_REPLY)
        self.assertEqual(len(self.services.tool_calls()), 2)
        self.assertEqual(len(self.services.model_requests()), 3)
        self.assertEqual(len(self.toolboxes), 1)
        for index, name in enumerate(self.services.tool_plan):
            self.assert_tool_call(name, index)
        self.assert_resources_closed()

    async def test_missing_either_source_fails_before_model_execution(self):
        for source in ("learn", WEB_SEARCH_TOOL):
            self.services.sources = {source}
            with self.assertRaisesRegex(ValueError, "both Microsoft Learn and native Web Search"):
                await answer(SETTINGS, "Read public docs.")
        self.assertFalse(self.services.model_requests())
        self.assert_resources_closed()

    async def test_write_unconfigured_and_unrelated_tools_fail_closed(self):
        for name in (
            "files.WriteFile",
            "files___WriteFile",
            "code_interpreter",
            "web_search_preview",
            "web.search",
            "web___search",
            "learn_microsoft_docs_search",
            "mail.SendMail",
        ):
            self.services.extra_tool = name
            with self.assertRaisesRegex(ValueError, "read-only allowlist"):
                await answer(SETTINGS, "Read public docs.")
        self.assertFalse(self.services.model_requests())
        self.assert_resources_closed()

    async def test_native_web_search_type_and_query_schema_are_required(self):
        valid = deepcopy(self.services.web_schema)
        invalid_schemas = (
            {**valid, "properties": {}},
            {**valid, "properties": {"search_query": {"type": "integer"}}},
            {**valid, "required": []},
        )
        for schema in invalid_schemas:
            self.services.web_schema = schema
            with self.assertRaisesRegex(ValueError, "required string search_query"):
                await answer(SETTINGS, "Search the public web.")
        self.services.web_schema = valid
        self.services.web_type = "mcp"
        with self.assertRaisesRegex(ValueError, "native Foundry Web Search"):
            await answer(SETTINGS, "Search the public web.")
        self.assertFalse(self.services.model_requests())
        self.assertFalse(self.services.tool_calls())
        self.assert_resources_closed()

    async def test_duplicate_wire_aliases_fail_before_model_or_tool_execution(self):
        for separator, other in ((".", "___"), ("___", ".")):
            self.services.tool_separator = separator
            for name in TOOL_ARGUMENTS:
                self.services.extra_tool = name.replace(".", other, 1)
                with self.assertRaisesRegex(ValueError, "multiple names"):
                    await answer(SETTINGS, "Read public docs.")
        self.assertFalse(self.services.model_requests())
        self.assertFalse(self.services.tool_calls())
        self.assert_resources_closed()

    async def test_concurrent_turns_never_share_toolbox_or_caller_context(self):
        async def turn(call_id):
            token = set_request_context(
                FoundryAgentRequestContext(
                    call_id=call_id,
                    session_id=f"session-{call_id}",
                    user_id=f"user-{call_id}",
                )
            )
            try:
                return await answer(SETTINGS, "Find documentation.")
            finally:
                reset_request_context(token)

        self.assertEqual(
            await asyncio.gather(turn("caller-a"), turn("caller-b")), [REPLY, REPLY]
        )
        self.assertEqual(len(self.toolboxes), 2)
        self.assertIsNot(self.toolboxes[0], self.toolboxes[1])
        for request, _ in self.services.requests:
            self.assertIn(request.headers[FOUNDRY_CALL_ID], ("caller-a", "caller-b"))
            self.assertNotIn(USER_ID, request.headers)
        self.assertEqual(
            set(self.contexts),
            {
                ("caller-a", "session-caller-a", "user-caller-a"),
                ("caller-b", "session-caller-b", "user-caller-b"),
            },
        )
        self.assert_resources_closed()

    async def test_turn_without_context_does_not_reuse_previous_headers(self):
        token = set_request_context(FoundryAgentRequestContext(call_id="first-caller"))
        try:
            await answer(SETTINGS, "Find documentation.")
        finally:
            reset_request_context(token)
        self.services.requests.clear()
        await answer(SETTINGS, "Another question.")
        self.assertTrue(
            all(FOUNDRY_CALL_ID not in request.headers for request, _ in self.services.requests)
        )
        self.assert_resources_closed()

    async def test_hosted_model_and_toolbox_use_same_managed_identity(self):
        with (
            patch.dict(os.environ, {"FOUNDRY_HOSTING_ENVIRONMENT": "hosted"}),
            patch("agent.toolbox.AzureCliCredential") as local,
        ):
            await answer(SETTINGS, "Find documentation.")
        local.assert_not_called()
        self.assertEqual(len(self.credentials), 1)
        self.assertIs(self.model_credentials[0], self.credentials[0])
        self.assertIs(self.toolbox_credentials[0], self.credentials[0])
        self.assert_resources_closed()

    async def test_local_execution_uses_azure_cli_for_both_boundaries(self):
        with patch("agent.toolbox.ManagedIdentityCredential") as hosted:
            await answer(SETTINGS, "Find documentation.")
        hosted.assert_not_called()
        self.assertIs(self.model_credentials[0], self.toolbox_credentials[0])
        self.assert_resources_closed()

    async def test_empty_toolbox_fails_before_model_execution(self):
        self.services.empty_tools = True
        with self.assertRaisesRegex(ValueError, "no tools"):
            await answer(SETTINGS, "Find documentation.")
        self.assertFalse(self.services.model_requests())
        self.assert_resources_closed()

    async def test_approval_required_tool_is_not_executed(self):
        for approval in ("always", {"never": False}):
            self.services.approval = approval
            for separator in (".", "___"):
                self.services.tool_separator = separator
                with self.assertRaisesRegex(ValueError, "approval flow"):
                    await answer(SETTINGS, "Find documentation.")
        self.assertFalse(self.services.model_requests())
        self.assertFalse(self.services.tool_calls())
        self.assert_resources_closed()

    async def test_native_web_search_approval_policy_is_not_bypassed(self):
        self.services.web_approval = "always"
        with self.assertRaisesRegex(ValueError, "approval flow"):
            await answer(SETTINGS, "Search the public web.")
        self.assertFalse(self.services.model_requests())
        self.assertFalse(self.services.tool_calls())
        self.assert_resources_closed()

    async def test_initialization_failure_closes_all_resources(self):
        self.services.fail_initialize = True
        with self.assertRaises(Exception):
            await answer(SETTINGS, "Find documentation.")
        self.assertFalse(self.services.model_requests())
        self.assert_resources_closed()

    async def test_failed_tool_cannot_be_presented_as_successful_lookup(self):
        self.services.fail_call = True
        for name in ("learn.microsoft_docs_search", WEB_SEARCH_TOOL):
            self.services.tool_plan = [name]
            with self.assertLogs(level="WARNING"):
                with self.assertRaisesRegex(RuntimeError, "toolbox tool failed"):
                    await answer(SETTINGS, "Read public docs.")
        self.assert_resources_closed()

    async def test_empty_model_reply_is_explicit_failure(self):
        self.services.empty_reply = True
        with self.assertRaisesRegex(RuntimeError, "no text response"):
            await answer(SETTINGS, "Find documentation.")
        self.assert_resources_closed()


class ActivityTests(_OfflineTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        with patch("agent.app.configure_observability"):
            self.host = build_app()
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.host), base_url="https://activity.test"
        )
        self.addAsyncCleanup(self.http.aclose)
        connector, token_client = MagicMock(), MagicMock()
        connector.close = AsyncMock()
        token_client.close = AsyncMock()
        for patcher in (
            patch.object(
                RestChannelServiceClientFactory,
                "create_connector_client",
                new_callable=AsyncMock,
                return_value=connector,
            ),
            patch.object(
                RestChannelServiceClientFactory,
                "create_user_token_client",
                new_callable=AsyncMock,
                return_value=token_client,
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def post_message(self, conversation_type="personal", text=None, mentions=None):
        payload = deepcopy(ACTIVITY)
        payload["conversation"]["conversationType"] = conversation_type
        if text is not None:
            payload["text"] = text
        if mentions:
            payload["entities"] = mentions
        return await self.http.post(
            "/activity/messages",
            json=payload,
            headers={
                FOUNDRY_CALL_ID: "activity-caller",
                SESSION_ID: "activity-session",
                USER_ID: "activity-user",
            },
        )

    async def test_activity_ingress_runs_real_loop_and_preserves_platform_context(self):
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            response = await self.post_message()
        self.assertEqual(response.status_code, 202, response.text)
        send.assert_awaited_once_with(REPLY)
        self.assertEqual(response.headers[SESSION_ID], "activity-session")
        for request, _ in self.services.requests:
            self.assertNotIn(USER_ID, request.headers)
            self.assertEqual(request.headers[FOUNDRY_CALL_ID], "activity-caller")
        self.assertEqual(
            self.contexts, [("activity-caller", "activity-session", "activity-user")]
        )
        self.assert_resources_closed()

    async def test_group_chat_and_mentioned_channel_are_supported(self):
        mention = {
            "type": "mention",
            "text": "<at>Docs</at>",
            "mentioned": {"id": "test-agent", "name": "Docs"},
        }
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            group = await self.post_message("groupChat")
            channel = await self.post_message(
                "channel", "<at>Docs</at> Find documentation.", [mention]
            )
        self.assertEqual(group.status_code, 202, group.text)
        self.assertEqual(channel.status_code, 202, channel.text)
        self.assertEqual(send.await_count, 2)
        self.assertNotIn("<at>Docs</at>", json.dumps(self.services.model_requests()[2][1]["input"]))
        self.assert_resources_closed()

    async def test_unmentioned_channel_is_ignored(self):
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            response = await self.post_message("channel")
        self.assertEqual(response.status_code, 202, response.text)
        send.assert_not_awaited()
        self.assertFalse(self.services.requests)

    async def test_empty_message_prompts_without_model_or_toolbox_call(self):
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            response = await self.post_message(text="   ")
        self.assertEqual(response.status_code, 202, response.text)
        send.assert_awaited_once_with(
            "Ask me about Microsoft documentation or current public web information."
        )
        self.assertFalse(self.services.requests)

    async def test_attachment_without_text_prompts_without_model_or_toolbox_call(self):
        payload = deepcopy(ACTIVITY)
        payload.pop("text")
        payload["attachments"] = [
            {
                "contentType": "image/png",
                "contentUrl": "https://example.invalid/image.png",
            }
        ]
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            response = await self.http.post(
                "/activity/messages",
                json=payload,
                headers={
                    FOUNDRY_CALL_ID: "activity-caller",
                    SESSION_ID: "activity-session",
                    USER_ID: "activity-user",
                },
            )
        self.assertEqual(response.status_code, 202, response.text)
        send.assert_awaited_once_with(
            "Ask me about Microsoft documentation or current public web information."
        )
        self.assertFalse(self.services.requests)

    async def test_toolbox_failure_logged_and_returns_safe_teams_error(self):
        self.services.empty_tools = True
        with (
            patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send,
            self.assertLogs("agent.app", level="ERROR") as logs,
        ):
            response = await self.post_message()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertIn("no tools", "\n".join(logs.output))
        self.assertIn("couldn't answer using the Foundry Toolbox", send.call_args.args[0])
        self.assertNotIn("Traceback", send.call_args.args[0])
        self.assert_resources_closed()

    async def test_readiness_and_malformed_activity(self):
        self.assertEqual((await self.http.get("/readiness")).status_code, 200)
        response = await self.http.post("/activity/messages", content="{")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.services.requests)

    async def test_web_search_executes_through_same_toolbox_as_learn_in_teams(self):
        for separator in (".", "___"):
            self.services.tool_separator = separator
            self.services.requests.clear()
            self.services.tool_plan = [
                "learn.microsoft_docs_search",
                WEB_SEARCH_TOOL,
            ]
            with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
                response = await self.post_message(text="Compare both public sources.")
            self.assertEqual(response.status_code, 202, response.text)
            send.assert_awaited_once_with(WEB_REPLY)
            self.assertEqual(len(self.services.tool_calls()), 2)
            for index, name in enumerate(self.services.tool_plan):
                self.assert_tool_call(name, index)
        self.assertEqual(len(self.toolboxes), 2)
        self.assert_resources_closed()

    async def test_concurrent_activities_keep_separate_connections_and_headers(self):
        payloads = []
        for index in range(2):
            payload = deepcopy(ACTIVITY)
            payload["id"] = f"human-{index}-turn"
            payload["from"] = {"id": f"human-{index}"}
            payloads.append(payload)
        with patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send:
            responses = await asyncio.gather(
                *(
                    self.http.post(
                        "/activity/messages",
                        json=payload,
                        headers={FOUNDRY_CALL_ID: f"human-{index}-call"},
                    )
                    for index, payload in enumerate(payloads)
                )
            )
        self.assertTrue(all(response.status_code == 202 for response in responses))
        self.assertEqual(send.await_count, 2)
        self.assertEqual(len(self.toolboxes), 2)
        self.assertIsNot(self.toolboxes[0], self.toolboxes[1])
        for requests in (self.services.mcp_requests(), self.services.model_requests()):
            self.assertEqual(
                {request.headers[FOUNDRY_CALL_ID] for request, _ in requests},
                {"human-0-call", "human-1-call"},
            )
            self.assertTrue(all(USER_ID not in request.headers for request, _ in requests))
        self.assert_resources_closed()

    async def test_web_search_failure_is_not_presented_as_success_in_teams(self):
        self.services.tool_plan = [WEB_SEARCH_TOOL]
        self.services.fail_call = True
        with (
            patch.object(TurnContext, "send_activity", new_callable=AsyncMock) as send,
            self.assertLogs("agent.app", level="ERROR"),
        ):
            response = await self.post_message(text="Search the public web.")
        self.assertEqual(response.status_code, 202, response.text)
        self.assertIn("couldn't answer", send.call_args.args[0])
        self.assertNotEqual(send.call_args.args[0], WEB_REPLY)
        self.assert_resources_closed()
