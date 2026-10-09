# Copyright (c) Microsoft. All rights reserved.

"""Offline, network-free tests for the Foundry toolbox integration in `main.py`.

Run with:

    cd src/claude-agent-sdk-invocations && python -m unittest discover tests

These tests never touch the network or require live Azure credentials:

* `claude_agent_sdk` is stubbed in `sys.modules` before each import of `main`
  (the real package costs ~40s to import and pulls in the Claude Code CLI
  wrapper, which is irrelevant to the toolbox-integration logic under test).
* `httpx.AsyncClient` is monkeypatched to an in-memory fake transport, so the
  "toolbox discovery" HTTP call never leaves the process.
* `main` is re-imported fresh (via `sys.modules` eviction) for every test
  because `TOOLBOX_ENDPOINT` / `TOOLBOX_ALLOWED_TOOLS` are resolved once, at
  module import time, from environment variables -- each scenario needs its
  own environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
import unittest
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Optional
from unittest import mock

import httpx
from starlette.requests import Request

# Put the agent source dir (the parent of tests/) on the path.
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from azure.ai.agentserver.core import FoundryAgentRequestContext  # noqa: E402

_BASE_ENV = {
    "FOUNDRY_PROJECT_ENDPOINT": "https://my-resource.services.ai.azure.com/api/projects/my-project",
    "ANTHROPIC_MODEL": "claude-test-model",
}
_TOOLBOX_ENV_VARS = ("TOOLBOX_ENDPOINT", "TOOLBOX_NAME", "TOOLBOX_ALLOWED_TOOLS")


# --------------------------------------------------------------------------
# Fakes / stubs
# --------------------------------------------------------------------------


@dataclass
class _FakeClaudeAgentOptions:
    permission_mode: Optional[str] = None
    model: Optional[str] = None
    include_partial_messages: Optional[bool] = None
    system_prompt: Optional[str] = None
    mcp_servers: Optional[dict] = None
    allowed_tools: Optional[list] = None


@dataclass
class _FakeMessage:
    type: str = "text"
    content: str = "ok"


def _install_fake_claude_agent_sdk():
    """Stub `claude_agent_sdk` so importing `main` is instant and offline."""
    fake = types.ModuleType("claude_agent_sdk")
    fake.ClaudeAgentOptions = _FakeClaudeAgentOptions

    async def _default_query(*, prompt, options):  # pragma: no cover - replaced per-test
        yield _FakeMessage()

    fake.query = _default_query
    sys.modules["claude_agent_sdk"] = fake


def _recording_query(bucket: list):
    """Build a fake `query()` that records the `options` it was called with."""

    async def _query(*, prompt, options):
        bucket.append({"prompt": prompt, "options": options})
        yield _FakeMessage()

    return _query


class _FakeHTTPResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_body: Optional[dict] = None,
        headers: Optional[dict] = None,
        text: str = "",
    ):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = {"content-type": "application/json", **(headers or {})}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_body

    async def aread(self):
        return self.text.encode("utf-8")

    async def aiter_lines(self):
        for line in self.text.splitlines():
            yield line


class _FakeAsyncClient:
    """Drop-in for `httpx.AsyncClient`, used only as an async context manager.

    `responses`, when set, is consumed in order (one entry per `post()` call,
    in the sequence: `initialize`, `notifications/initialized`, then one
    `tools/list` page per entry) so tests can exercise the MCP handshake and
    pagination. When empty/unset, every call gets `default_response`.
    """

    calls: list = []
    default_response: Any = _FakeHTTPResponse(200, {"result": {"tools": []}})
    responses: list = []
    delete_calls: list = []
    delete_response: Any = _FakeHTTPResponse(405)

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.calls.append({"url": url, "headers": headers, "json": json})
        if _FakeAsyncClient.responses:
            response = _FakeAsyncClient.responses.pop(0)
        else:
            response = _FakeAsyncClient.default_response
        if json and "id" in json and response.headers.get("content-type") == "application/json":
            response = _FakeHTTPResponse(
                response.status_code,
                dict(response._json_body),
                dict(response.headers),
                response.text,
            )
            response._json_body.setdefault("id", json["id"])
        return response

    @asynccontextmanager
    async def stream(self, method, url, headers=None, json=None):
        response = await self.post(url, headers=headers, json=json)
        yield response

    async def delete(self, url, headers=None):
        _FakeAsyncClient.delete_calls.append({"url": url, "headers": headers})
        return _FakeAsyncClient.delete_response


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


@contextmanager
def _toolbox_env(**overrides):
    """Set env vars for one test, restoring the prior environment afterward."""
    env = dict(_BASE_ENV)
    env.update(overrides)
    tracked_keys = set(env) | set(_TOOLBOX_ENV_VARS)
    saved = {k: os.environ.get(k) for k in tracked_keys}
    for key in _TOOLBOX_ENV_VARS:
        os.environ.pop(key, None)
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _import_main():
    _install_fake_claude_agent_sdk()
    sys.modules.pop("main", None)
    import main as main_module  # noqa: PLC0415

    return main_module


def _make_request(body: bytes) -> Request:
    scope = {"type": "http", "method": "POST", "headers": []}
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


async def _invoke(main_module, body: bytes = b"hello") -> list:
    response = await main_module.handle_invoke(_make_request(body))
    events = []
    async for chunk in response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, (bytes, bytearray)) else chunk
        assert text.startswith("data: ") and text.endswith("\n\n")
        events.append(json.loads(text[len("data: "):-2]))
    return events


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class ToolboxAbsentTests(unittest.TestCase):
    """(a) Absent optional toolbox preserves base (no-toolbox) behavior."""

    def test_no_toolbox_env_means_no_toolbox_integration(self):
        with _toolbox_env():
            main = _import_main()
            self.assertIsNone(main.TOOLBOX_ENDPOINT)
            self.assertEqual(main.TOOLBOX_ALLOWED_TOOLS, [])

            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = []
                events = asyncio.run(_invoke(main))

            self.assertEqual(_FakeAsyncClient.calls, [])  # no discovery call made
            self.assertEqual(len(calls), 1)
            options = calls[0]["options"]
            self.assertIsNone(options.mcp_servers)
            self.assertIsNone(options.allowed_tools)
            self.assertEqual(events, [{"type": "text", "content": "ok"}])


class AllowlistConfigurationTests(unittest.TestCase):
    """(c)/(part of #2) Configured toolbox requires a non-empty allowlist."""

    def test_toolbox_endpoint_without_allowlist_raises_at_import(self):
        with _toolbox_env(TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp"):
            with self.assertRaises(EnvironmentError):
                _import_main()
        # A failed module body leaves no partial "main" entry behind;
        # confirm the next import in another test starts clean.
        self.assertNotIn("main", sys.modules)


class DiscoveryFailureTests(unittest.TestCase):
    """(b) Configured discovery failure surfaces as an explicit invocation
    failure -- never a silent, success-shaped fallback."""

    def test_discovery_http_error_fails_invocation_with_no_fallback(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = []
                _FakeAsyncClient.default_response = _FakeHTTPResponse(500)
                events = asyncio.run(_invoke(main))

            self.assertEqual(len(events), 1)
            self.assertIn("error", events[0])
            self.assertIn("toolbox integration failed", events[0]["error"])
            self.assertIn("HTTP 500", events[0]["error"])
            # The agent/model was never invoked: a discovery failure must not
            # produce a success-shaped answer.
            self.assertEqual(calls, [])


class UnknownAllowlistEntryTests(unittest.TestCase):
    """(c) Unknown/missing allowlist entries are rejected, not skipped."""

    def test_allowlist_entry_not_in_discovery_is_rejected(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="unknown_tool",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = []
                _FakeAsyncClient.default_response = _FakeHTTPResponse(
                    200, {"result": {"tools": [{"name": "web_search"}]}}
                )
                events = asyncio.run(_invoke(main))

            self.assertEqual(len(events), 1)
            self.assertIn("not returned by toolbox discovery", events[0]["error"])
            self.assertIn("unknown_tool", events[0]["error"])
            self.assertEqual(calls, [])


class WriteToolNotExposedTests(unittest.TestCase):
    """(d) A discovered write/mutating tool outside the allowlist is never
    exposed, even though discovery returned it."""

    def test_discovered_tool_outside_allowlist_is_never_allowed(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = []
                _FakeAsyncClient.default_response = _FakeHTTPResponse(
                    200,
                    {"result": {"tools": [{"name": "web_search"}, {"name": "delete_file"}]}},
                )
                asyncio.run(_invoke(main))

            self.assertEqual(len(calls), 1)
            allowed = calls[0]["options"].allowed_tools
            self.assertEqual(allowed, [f"mcp__{main.TOOLBOX_SERVER_LABEL}__web_search"])
            self.assertNotIn(f"mcp__{main.TOOLBOX_SERVER_LABEL}__delete_file", allowed)


class CallIdPropagationTests(unittest.TestCase):
    """(e) x-agent-foundry-call-id propagates into both the discovery call
    and the native MCP HTTP config."""

    def test_call_id_forwarded_to_discovery_and_mcp_config(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            ctx = FoundryAgentRequestContext(call_id="call-abc-123")
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(main, "get_request_context", lambda: ctx), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = []
                _FakeAsyncClient.default_response = _FakeHTTPResponse(
                    200, {"result": {"tools": [{"name": "web_search"}]}}
                )
                asyncio.run(_invoke(main))

            # initialize, notifications/initialized, tools/list -- the call
            # ID and feature header must be present from the very first
            # (initialize) call, not only on tools/list.
            self.assertEqual(len(_FakeAsyncClient.calls), 3)
            self.assertEqual(
                _FakeAsyncClient.calls[0]["headers"]["x-agent-foundry-call-id"], "call-abc-123"
            )
            mcp_headers = calls[0]["options"].mcp_servers[main.TOOLBOX_SERVER_LABEL]["headers"]
            self.assertEqual(mcp_headers["x-agent-foundry-call-id"], "call-abc-123")
            # Also carries the protocol-reference feature header on both.
            self.assertEqual(
                _FakeAsyncClient.calls[0]["headers"]["Foundry-Features"], "Toolboxes=V1Preview"
            )
            self.assertEqual(mcp_headers["Foundry-Features"], "Toolboxes=V1Preview")


class McpHandshakeTests(unittest.TestCase):
    """MCP lifecycle: `initialize` + `notifications/initialized` must precede
    `tools/list`, and any assigned `mcp-session-id` must be carried on
    subsequent calls."""

    def test_initialize_and_initialized_precede_tools_list(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}, headers={"mcp-session-id": "sess-1"}),
                    _FakeHTTPResponse(200, {}),
                    _FakeHTTPResponse(200, {"result": {"tools": [{"name": "web_search"}]}}),
                ]
                asyncio.run(_invoke(main))

            methods = [c["json"]["method"] for c in _FakeAsyncClient.calls]
            self.assertEqual(methods, ["initialize", "notifications/initialized", "tools/list"])
            # The session id assigned during initialize must be forwarded on
            # every subsequent call.
            self.assertEqual(_FakeAsyncClient.calls[1]["headers"]["mcp-session-id"], "sess-1")
            self.assertEqual(_FakeAsyncClient.calls[2]["headers"]["mcp-session-id"], "sess-1")
            self.assertNotIn("mcp-session-id", _FakeAsyncClient.calls[0]["headers"])

    def test_sse_responses_and_required_accept_header_are_supported(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.delete_response = _FakeHTTPResponse(200)
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(
                        200,
                        headers={"content-type": "text/event-stream", "mcp-session-id": "sess-sse"},
                        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n',
                    ),
                    _FakeHTTPResponse(202),
                    _FakeHTTPResponse(
                        200,
                        headers={"content-type": "text/event-stream"},
                        text=(
                            'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
                            'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search"}]}}\n\n'
                        ),
                    ),
                ]
                events = asyncio.run(_invoke(main))

            self.assertEqual(events, [{"type": "text", "content": "ok"}])
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(_FakeAsyncClient.delete_calls), 1)
            self.assertTrue(
                all(
                    call["headers"]["Accept"] == "application/json, text/event-stream"
                    for call in _FakeAsyncClient.calls
                )
            )

    def test_initialized_notification_failure_terminates_assigned_session(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.delete_response = _FakeHTTPResponse(200)
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}, headers={"mcp-session-id": "sess-failed"}),
                    _FakeHTTPResponse(500),
                ]
                events = asyncio.run(_invoke(main))

            self.assertIn("toolbox integration failed", events[0]["error"])
            self.assertEqual(calls, [])
            self.assertEqual(len(_FakeAsyncClient.delete_calls), 1)
            self.assertEqual(
                _FakeAsyncClient.delete_calls[0]["headers"]["mcp-session-id"], "sess-failed"
            )


class ToolsListPaginationTests(unittest.TestCase):
    """`tools/list` is cursor-paginated: every page must be requested before
    validating the allowlist, or a tool on a later page is wrongly reported
    unknown."""

    def test_all_pages_are_collected_before_allowlist_validation(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="second_page_tool",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}),  # initialize
                    _FakeHTTPResponse(200, {}),  # notifications/initialized
                    _FakeHTTPResponse(
                        200,
                        {
                            "result": {
                                "tools": [{"name": "web_search"}],
                                "nextCursor": "page-2",
                            }
                        },
                    ),
                    _FakeHTTPResponse(
                        200, {"result": {"tools": [{"name": "second_page_tool"}]}}
                    ),
                ]
                asyncio.run(_invoke(main))

            tools_list_calls = [c for c in _FakeAsyncClient.calls if c["json"]["method"] == "tools/list"]
            self.assertEqual(len(tools_list_calls), 2)
            self.assertEqual(tools_list_calls[1]["json"]["params"], {"cursor": "page-2"})
            # The tool from the second page was validated and allowed.
            self.assertEqual(len(calls), 1)
            allowed = calls[0]["options"].allowed_tools
            self.assertEqual(allowed, [f"mcp__{main.TOOLBOX_SERVER_LABEL}__second_page_tool"])


class DiscoverySessionTerminationTests(unittest.TestCase):
    """The discovery-only MCP session is always terminated after discovery,
    whether or not the server supports termination, and termination failures
    never turn a successful discovery into a failed invocation."""

    def test_session_terminated_after_discovery_with_session_id(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.delete_response = _FakeHTTPResponse(200)
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}, headers={"mcp-session-id": "sess-1"}),
                    _FakeHTTPResponse(200, {}),
                    _FakeHTTPResponse(200, {"result": {"tools": [{"name": "web_search"}]}}),
                ]
                asyncio.run(_invoke(main))

            # Discovery succeeded (the model was invoked) and the session
            # assigned during initialize was explicitly terminated.
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(_FakeAsyncClient.delete_calls), 1)
            self.assertEqual(
                _FakeAsyncClient.delete_calls[0]["headers"]["mcp-session-id"], "sess-1"
            )

    def test_no_termination_call_when_no_session_id_assigned(self):
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}),  # initialize, no session id
                    _FakeHTTPResponse(200, {}),
                    _FakeHTTPResponse(200, {"result": {"tools": [{"name": "web_search"}]}}),
                ]
                asyncio.run(_invoke(main))

            self.assertEqual(len(calls), 1)
            self.assertEqual(_FakeAsyncClient.delete_calls, [])

    def test_405_on_termination_is_tolerated_not_raised(self):
        """A server that doesn't support termination replies 405; discovery
        must still succeed and the invocation must not fail."""
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []
            with mock.patch.object(httpx, "AsyncClient", _FakeAsyncClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.delete_response = _FakeHTTPResponse(405)
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}, headers={"mcp-session-id": "sess-1"}),
                    _FakeHTTPResponse(200, {}),
                    _FakeHTTPResponse(200, {"result": {"tools": [{"name": "web_search"}]}}),
                ]
                events = asyncio.run(_invoke(main))

            self.assertEqual(len(_FakeAsyncClient.delete_calls), 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(events, [{"type": "text", "content": "ok"}])

    def test_termination_error_is_logged_not_raised(self):
        """A non-405 error terminating the session is caught and logged, and
        must not fail an otherwise-successful discovery/invocation."""
        with _toolbox_env(
            TOOLBOX_ENDPOINT="https://toolbox.example.com/mcp",
            TOOLBOX_ALLOWED_TOOLS="web_search",
        ):
            main = _import_main()
            calls: list = []

            class _RaisingDeleteClient(_FakeAsyncClient):
                async def delete(self, url, headers=None):
                    _FakeAsyncClient.delete_calls.append({"url": url, "headers": headers})
                    raise httpx.ConnectError("boom", request=httpx.Request("DELETE", url))

            with mock.patch.object(httpx, "AsyncClient", _RaisingDeleteClient), mock.patch.object(
                main, "query", _recording_query(calls)
            ), mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ), mock.patch.object(main, "logger") as mock_logger:
                _FakeAsyncClient.calls = []
                _FakeAsyncClient.delete_calls = []
                _FakeAsyncClient.responses = [
                    _FakeHTTPResponse(200, {"result": {}}, headers={"mcp-session-id": "sess-1"}),
                    _FakeHTTPResponse(200, {}),
                    _FakeHTTPResponse(200, {"result": {"tools": [{"name": "web_search"}]}}),
                ]
                events = asyncio.run(_invoke(main))

            self.assertEqual(len(_FakeAsyncClient.delete_calls), 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(events, [{"type": "text", "content": "ok"}])
            mock_logger.warning.assert_called_once()


class AuthScopeAndQueryPreservationTests(unittest.TestCase):
    """(f) Correct auth scope and toolbox-endpoint query-string handling."""

    def test_auth_scope_is_ai_azure_com_default(self):
        with _toolbox_env():
            main = _import_main()
            self.assertEqual(main._TOOLBOX_SCOPE, "https://ai.azure.com/.default")

    def test_ensure_api_version_appends_when_absent(self):
        with _toolbox_env():
            main = _import_main()
            self.assertEqual(
                main._ensure_api_version("https://toolbox.example.com/mcp"),
                "https://toolbox.example.com/mcp?api-version=v1",
            )

    def test_ensure_api_version_preserves_existing_query_string(self):
        with _toolbox_env():
            main = _import_main()
            self.assertEqual(
                main._ensure_api_version("https://toolbox.example.com/mcp?foo=bar"),
                "https://toolbox.example.com/mcp?foo=bar&api-version=v1",
            )

    def test_ensure_api_version_is_idempotent(self):
        with _toolbox_env():
            main = _import_main()
            url = "https://toolbox.example.com/mcp?api-version=v1"
            self.assertEqual(main._ensure_api_version(url), url)


class AuthorizationHeaderRegressionTests(unittest.TestCase):
    """(g) Regression guard: the Authorization header must be the real
    bearer token, never a placeholder/masked value."""

    def test_authorization_header_is_real_bearer_token(self):
        with _toolbox_env():
            main = _import_main()
            with mock.patch.object(
                main, "_get_toolbox_token_provider", lambda: (lambda: "FAKE_TOKEN_VALUE")
            ):
                headers = main._toolbox_headers()
            self.assertEqual(headers["Authorization"], "Bearer FAKE_TOKEN_VALUE")


if __name__ == "__main__":
    unittest.main()
