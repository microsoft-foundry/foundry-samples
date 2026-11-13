from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from foundry_m365_autopilot.agent import (
    BASIC_MCP_SERVERS,
    FoundryDigitalWorkerAgent,
)
from foundry_m365_autopilot.activity_context import (
    build_activity_context_attachment,
    format_activity_context,
)
from foundry_m365_autopilot.capabilities import build_capabilities_attachment


class BasicMcpTests(unittest.IsolatedAsyncioTestCase):
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

    def tearDown(self) -> None:
        self.environment.stop()

    def test_manifest_contains_only_basic_servers(self) -> None:
        labels = tuple(
            server["mcpServerName"] for server in self.agent._mcp_servers
        )
        self.assertEqual(labels, BASIC_MCP_SERVERS)

    async def test_build_tools_returns_only_remote_mcp_descriptors(self) -> None:
        auth = SimpleNamespace(
            exchange_token=AsyncMock(return_value=SimpleNamespace(token="token"))
        )
        tools = await self.agent._build_mcp_tools(
            auth,
            "AGENTIC",
            SimpleNamespace(),
            allowed_labels=BASIC_MCP_SERVERS,
        )

        self.assertEqual(len(tools), 3)
        self.assertTrue(all(tool["type"] == "mcp" for tool in tools))
        self.assertEqual(
            {tool["server_label"] for tool in tools}, set(BASIC_MCP_SERVERS)
        )
        self.assertFalse(any(tool["type"] == "function" for tool in tools))

    async def test_unknown_server_cannot_be_enabled(self) -> None:
        self.agent._mcp_servers.append(
            {
                "mcpServerName": "untrusted-server",
                "url": "https://untrusted.example/mcp",
            }
        )
        tools = await self.agent._build_mcp_tools(
            None,
            None,
            SimpleNamespace(),
            allowed_labels=BASIC_MCP_SERVERS,
        )
        self.assertNotIn(
            "untrusted-server", {tool["server_label"] for tool in tools}
        )

    def test_request_contains_no_local_function_tools(self) -> None:
        tools = [
            {
                "type": "mcp",
                "server_label": label,
                "server_url": f"https://example.test/{label}",
            }
            for label in BASIC_MCP_SERVERS
        ]
        request = {
            "model": self.agent._deployment,
            "instructions": "test",
            "input": "test",
            "tools": tools,
        }
        serialized = json.dumps(request)
        self.assertNotIn('"type": "function"', serialized)

    async def test_model_classifies_capabilities_without_tools(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {"output_text": "CAPABILITIES"},
        )
        self.agent._http_client = SimpleNamespace(
            post=AsyncMock(return_value=response)
        )

        intent = await self.agent.classify_user_intent("你能做什么？")

        self.assertEqual(intent, self.agent.CAPABILITIES_INTENT)
        request = self.agent._http_client.post.await_args.kwargs["json"]
        self.assertNotIn("tools", request)
        self.assertEqual(request["input"], "你能做什么？")

    async def test_model_classification_failure_defaults_to_other(self) -> None:
        response = SimpleNamespace(status_code=500)
        self.agent._http_client = SimpleNamespace(
            post=AsyncMock(return_value=response)
        )

        intent = await self.agent.classify_user_intent("Send a status update")

        self.assertEqual(intent, self.agent.OTHER_INTENT)

    def test_builds_fixed_capabilities_adaptive_card(self) -> None:
        attachment = build_capabilities_attachment()
        card = attachment["content"]
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertEqual(card["type"], "AdaptiveCard")
        sections = [item for item in card["body"] if item["type"] == "Container"]
        self.assertEqual(len(sections), 3)
        self.assertIn("Mail", serialized)
        self.assertIn("Teams", serialized)
        self.assertIn("Calendar", serialized)

    def test_response_id_is_scoped_by_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.agent._response_store_dir = Path(directory)
            self.agent._save_response_id("conversation-a", {"id": "response-a"})
            self.assertEqual(
                self.agent._load_previous_response_id("conversation-a"),
                "response-a",
            )
            self.assertIsNone(
                self.agent._load_previous_response_id("conversation-b")
            )

    def test_formats_activity_context_without_full_identifiers(self) -> None:
        activity = SimpleNamespace(
            channel_id="msteams",
            locale="en-US",
            service_url="https://service.example/tenant/conversation",
            channel_data={"tenant": {"id": "tenant-id"}},
            from_property=SimpleNamespace(
                name="Alex Wilber",
                id="29:1234567890abcdefghijklmnopqrstuvwxyz",
                aad_object_id="00000000-1111-2222-3333-444444444444",
            ),
            conversation=SimpleNamespace(
                id="19:abcdefghijklmnopqrstuvwxyz0123456789@thread.v2",
                conversation_type="personal",
            ),
            recipient=SimpleNamespace(
                tenant_id="11111111-2222-3333-4444-555555555555",
                agentic_app_id="agent-app-id-abcdefghijklmnopqrstuvwxyz",
                agentic_user_id="agent-user-id-abcdefghijklmnopqrstuvwxyz",
            ),
        )

        summary = format_activity_context(activity)

        self.assertIn("Activity context", summary)
        self.assertIn("Display name: Alex Wilber", summary)
        self.assertIn("Channel: msteams", summary)
        self.assertIn("Conversation type: personal", summary)
        self.assertIn("Service URL: present", summary)
        self.assertIn("Agent user id:", summary)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", summary)
        self.assertNotIn("00000000-1111-2222-3333-444444444444", summary)

    def test_builds_activity_context_adaptive_card(self) -> None:
        activity = SimpleNamespace(
            channel_id="msteams",
            locale="en-US",
            service_url="https://service.example/tenant/conversation",
            channel_data={"tenant": {"id": "tenant-id"}},
            from_property=SimpleNamespace(
                name="Alex Wilber",
                id="29:1234567890abcdefghijklmnopqrstuvwxyz",
                aad_object_id="00000000-1111-2222-3333-444444444444",
            ),
            conversation=SimpleNamespace(
                id="19:abcdefghijklmnopqrstuvwxyz0123456789@thread.v2",
                conversation_type="personal",
            ),
            recipient=SimpleNamespace(
                tenant_id="11111111-2222-3333-4444-555555555555",
                agentic_app_id="agent-app-id-abcdefghijklmnopqrstuvwxyz",
                agentic_user_id="agent-user-id-abcdefghijklmnopqrstuvwxyz",
            ),
        )

        session_id = "session-1234567890abcdefghijklmnopqrstuvwxyz"
        attachment = build_activity_context_attachment(
            activity, session_id=session_id
        )
        card = attachment["content"]
        serialized = json.dumps(attachment)

        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertIn("User", serialized)
        self.assertIn("Conversation", serialized)
        self.assertIn("Digital Worker", serialized)
        self.assertIn("Alex Wilber", serialized)
        self.assertIn(session_id, serialized)
        sections = [item for item in card["body"] if item["type"] == "Container"]
        self.assertEqual(len(sections), 3)
        self.assertTrue(
            all(
                section["style"] == "emphasis" and section["separator"]
                for section in sections
            )
        )
        self.assertIn("msteams", serialized)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", serialized)
        self.assertNotIn("00000000-1111-2222-3333-444444444444", serialized)


if __name__ == "__main__":
    unittest.main()
