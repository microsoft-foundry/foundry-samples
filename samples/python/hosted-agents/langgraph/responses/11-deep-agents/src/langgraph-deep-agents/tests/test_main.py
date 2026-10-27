"""Verify default model client ownership without Azure or model requests."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from azure.identity import DefaultAzureCredential
from langchain.agents.middleware import TodoListMiddleware
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from openai import OpenAI

SAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SAMPLE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "deep_research_main", SAMPLE_DIR / "main.py"
)
assert SPEC is not None and SPEC.loader is not None
main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(main)


class MainLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def test_agent_uses_default_backend_and_keeps_todo_middleware(self) -> None:
        with patch("agent.create_deep_agent") as create_agent:
            main.build_agent(MagicMock(), MagicMock(), [], MagicMock())
        options = create_agent.call_args.kwargs
        self.assertNotIn("backend", options)
        self.assertEqual(
            [type(middleware) for middleware in options["middleware"]],
            [TodoListMiddleware],
        )

    async def exercise(
        self, failure: str | None, *, tracing_disabled: bool = False
    ) -> None:
        credential = MagicMock(spec=DefaultAzureCredential)
        credential.__enter__.return_value = credential
        credential.__exit__.return_value = False
        project = MagicMock()
        endpoint = OpenAI(
            base_url=f"https://model-{uuid4().hex}.invalid/openai/v1",
            api_key="test-token",
        )
        project.get_openai_client.return_value = endpoint
        saver = MagicMock()
        saver.__aenter__ = AsyncMock(return_value=saver)
        saver.__aexit__ = AsyncMock(return_value=False)
        models: list[AzureAIOpenAIApiChatModel] = []

        def close_credential(*exception: Any) -> bool:
            for model in models:
                self.assertTrue(model.root_client.is_closed())
                self.assertTrue(model.root_async_client.is_closed())
            return False

        credential.__exit__.side_effect = close_credential

        def create_model(**options: Any) -> AzureAIOpenAIApiChatModel:
            self.assertNotIn("http_client", options)
            self.assertNotIn("http_async_client", options)
            self.assertNotIn("base_url", options)
            self.assertNotIn("api_key", options)
            self.assertEqual(
                options["project_endpoint"], "https://example.invalid/project"
            )
            self.assertIs(options["credential"], credential)
            if failure == "model":
                raise RuntimeError("model failed")
            model = AzureAIOpenAIApiChatModel(**options)
            models.append(model)
            return model

        async def load_tools(received: Any) -> list[Any]:
            self.assertIs(received, credential)
            self.assertFalse(models[0].root_client.is_closed())
            self.assertFalse(models[0].root_async_client.is_closed())
            if failure == "tools":
                raise RuntimeError("tools failed")
            return []

        async def run_host(**options: Any) -> None:
            self.assertEqual(options, {})
            self.assertFalse(models[0].root_client.is_closed())
            self.assertFalse(models[0].root_async_client.is_closed())
            credential.__exit__.assert_not_called()
            saver.__aexit__.assert_not_awaited()
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "run":
                raise RuntimeError("run failed")

        tracing = MagicMock()
        graph = MagicMock()
        export_tool = MagicMock()
        host = MagicMock(return_value=MagicMock(run_async=run_host))
        if failure == "tracing":
            tracing.side_effect = RuntimeError("tracing failed")
        if failure == "endpoint":
            project.get_openai_client.side_effect = RuntimeError("endpoint failed")
        if failure == "checkpoint":
            saver.__aenter__.side_effect = RuntimeError("checkpoint failed")
        if failure == "checkpoint_exit":
            saver.__aexit__.side_effect = RuntimeError("checkpoint_exit failed")
        if failure == "graph":
            graph.side_effect = RuntimeError("graph failed")
        if failure == "export":
            export_tool.side_effect = RuntimeError("export failed")
        if failure == "host":
            host.side_effect = RuntimeError("host failed")
        with ExitStack() as resources:
            resources.enter_context(
                patch(
                    "langchain_azure_ai._resources.AIProjectClient",
                    return_value=project,
                )
            )
            resources.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "FOUNDRY_PROJECT_ENDPOINT": "https://example.invalid/project",
                        "OTEL_SDK_DISABLED": "true" if tracing_disabled else "false",
                        "PORT": "8088",
                    },
                )
            )
            for name in (
                "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
            ):
                os.environ.pop(name, None)
            for name, value in {
                "load_dotenv": MagicMock(),
                "DefaultAzureCredential": MagicMock(return_value=credential),
                "enable_auto_tracing": tracing,
                "AzureAIOpenAIApiChatModel": create_model,
                "load_tools": load_tools,
                "FoundryCheckpointSaver": MagicMock(return_value=saver),
                "create_report_export_tool": export_tool,
                "build_agent": graph,
                "ResponsesHostServer": host,
            }.items():
                resources.enter_context(patch.object(main, name, value))
            try:
                if failure == "cancel":
                    with self.assertRaises(asyncio.CancelledError):
                        await main.main()
                elif failure:
                    with self.assertRaisesRegex(RuntimeError, f"{failure} failed"):
                        await main.main()
                else:
                    await main.main()
                credential.__exit__.assert_called_once()
                for model in models:
                    self.assertTrue(model.root_client.is_closed())
                    self.assertTrue(model.root_async_client.is_closed())
                    self.assertTrue(model.use_responses_api)
                    self.assertEqual(model.output_version, "responses/v1")
                    self.assertTrue(endpoint.is_closed())
                if failure not in {
                    "tracing",
                    "endpoint",
                    "model",
                    "tools",
                    "checkpoint",
                }:
                    saver.__aexit__.assert_awaited_once()
                if tracing_disabled:
                    tracing.assert_not_called()
                else:
                    tracing.assert_called_once_with(
                        credential=credential, auto_configure_azure_monitor=True
                    )
                self.assertEqual(
                    os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"],
                    "false",
                )
                self.assertEqual(
                    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"],
                    "false",
                )
            finally:
                endpoint.close()
                for model in models:
                    model.root_client.close()
                    await model.root_async_client.close()

    async def test_shutdown_closes_default_clients_and_credential(self) -> None:
        await self.exercise(None)

    async def test_startup_and_host_failures_close_owned_resources(self) -> None:
        for failure in (
            "tracing",
            "endpoint",
            "model",
            "tools",
            "checkpoint",
            "graph",
            "export",
            "host",
            "run",
            "checkpoint_exit",
        ):
            with self.subTest(failure=failure):
                await self.exercise(failure)

    async def test_host_cancellation_closes_owned_resources(self) -> None:
        await self.exercise("cancel")

    async def test_disabled_tracing_does_not_change_resource_ownership(self) -> None:
        await self.exercise(None, tracing_disabled=True)


if __name__ == "__main__":
    unittest.main()
