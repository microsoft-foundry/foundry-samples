import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


AGENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent-framework-agent-basic-responses-byoaks"
    / "main.py"
)


class AgentCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.agent = Mock()
        self.foundry_client = Mock()
        self.openai_client = Mock()
        self.server = Mock()
        self.sync_credential = Mock()
        self.async_credential = Mock()
        self.async_credential.get_token = AsyncMock(
            return_value=types.SimpleNamespace(token="test-token")
        )

        modules = {}
        for name in (
            "agent_framework",
            "agent_framework.foundry",
            "agent_framework.openai",
            "agent_framework_foundry_hosting",
            "azure",
            "azure.identity",
            "azure.identity.aio",
            "dotenv",
        ):
            modules[name] = types.ModuleType(name)
        modules["agent_framework"].Agent = self.agent
        modules["agent_framework.foundry"].FoundryChatClient = self.foundry_client
        modules["agent_framework.openai"].OpenAIChatCompletionClient = self.openai_client
        modules["agent_framework_foundry_hosting"].ResponsesHostServer = self.server
        modules["azure.identity"].DefaultAzureCredential = Mock(return_value=self.sync_credential)
        modules["azure.identity.aio"].DefaultAzureCredential = Mock(return_value=self.async_credential)
        modules["dotenv"].load_dotenv = Mock()

        spec = importlib.util.spec_from_file_location("byo_aks_agent", AGENT_PATH)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.module)

    def test_gpt_oss_uses_account_chat_endpoint_and_async_token(self):
        env = {
            "AZURE_AI_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/demo",
        }
        with patch.dict(os.environ, env, clear=True):
            self.module._create_client("gpt-oss-120b")

        kwargs = self.openai_client.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-oss-120b")
        self.assertEqual(kwargs["base_url"], "https://example.services.ai.azure.com/openai/v1/")
        self.assertEqual(asyncio.run(kwargs["api_key"]()), "test-token")
        self.async_credential.get_token.assert_awaited_once_with(
            "https://cognitiveservices.azure.com/.default"
        )
        self.foundry_client.assert_not_called()

    def test_explicit_openai_endpoint_overrides_project_hostname(self):
        env = {
            "FOUNDRY_PROJECT_ENDPOINT": "https://project.example/api/projects/demo",
            "AZURE_OPENAI_ENDPOINT": "https://account.example/",
        }
        with patch.dict(os.environ, env, clear=True):
            self.module._create_client("GPT-OSS-120B")
        self.assertEqual(self.openai_client.call_args.kwargs["base_url"], "https://account.example/openai/v1/")

    def test_non_gpt_oss_uses_foundry_client(self):
        env = {"FOUNDRY_PROJECT_ENDPOINT": "https://project.example/api/projects/demo"}
        with patch.dict(os.environ, env, clear=True):
            self.module._create_client("other-model")
        self.foundry_client.assert_called_once_with(
            project_endpoint=env["FOUNDRY_PROJECT_ENDPOINT"],
            model="other-model",
            credential=self.sync_credential,
        )
        self.openai_client.assert_not_called()

    def test_chat_options_drop_responses_only_fields(self):
        options = {
            "temperature": 0.2,
            "max_completion_tokens": 64,
            "store": False,
            "previous_response_id": "response-id",
            "unsupported": "value",
        }
        self.assertEqual(
            self.module._filter_chat_completion_options(None, options),
            {"temperature": 0.2, "max_completion_tokens": 64},
        )

    def test_server_installs_filter_only_for_gpt_oss(self):
        env = {
            "FOUNDRY_PROJECT_ENDPOINT": "https://project.example/api/projects/demo",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-oss-120b",
        }
        with patch.dict(os.environ, env, clear=True):
            self.module.main()
        self.assertIsNone(self.agent.call_args.kwargs["default_options"])
        self.assertIs(
            self.server.call_args.kwargs["prepare_options"],
            self.module._filter_chat_completion_options,
        )
        self.server.return_value.run.assert_called_once_with()

        self.server.reset_mock()
        env["AZURE_AI_MODEL_DEPLOYMENT_NAME"] = "other-model"
        with patch.dict(os.environ, env, clear=True):
            self.module.main()
        self.assertEqual(self.agent.call_args.kwargs["default_options"], {"store": False})
        self.assertIsNone(self.server.call_args.kwargs["prepare_options"])

    def test_missing_model_or_project_endpoint_fails_explicitly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Model deployment name"):
                self.module.main()
            with self.assertRaisesRegex(RuntimeError, "Project endpoint"):
                self.module._create_client("gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()
