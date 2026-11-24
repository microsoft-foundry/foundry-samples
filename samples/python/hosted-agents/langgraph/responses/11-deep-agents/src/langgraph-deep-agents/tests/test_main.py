"""Verify additive Blob-tool wiring without changing the existing agent setup."""

from __future__ import annotations

import io
import logging
import os
import sys
import unittest
from contextlib import ExitStack
from itertools import product
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent
import main


class BlobToolWiringTests(unittest.TestCase):
    def test_research_only_prompt_omits_publication_instructions(self) -> None:
        for explicit_none in (False, True):
            with (
                self.subTest(explicit_none=explicit_none),
                patch.object(agent, "create_deep_agent") as create,
            ):
                tools = [MagicMock()]
                arguments = {"report_export_tool": None} if explicit_none else {}
                agent.build_agent(MagicMock(), MagicMock(), tools, **arguments)
                instructions = create.call_args.kwargs["system_prompt"]
                self.assertNotIn("publish_report", instructions)
                self.assertNotIn("## Report publication", instructions)
                self.assertNotIn("7. **Publish**", instructions)
                self.assertIn("6. **Verify**", instructions)
                self.assertIn("## Report Writing Guidelines", instructions)
                self.assertIs(create.call_args.kwargs["tools"], tools)

    def test_export_tool_enables_publication_step_and_revision_instructions(
        self,
    ) -> None:
        export_tool = MagicMock()
        export_tool.__bool__.return_value = False
        tools = [MagicMock()]
        with patch.object(agent, "create_deep_agent") as create:
            agent.build_agent(MagicMock(), MagicMock(), tools, export_tool)
            instructions = create.call_args.kwargs["system_prompt"]
            self.assertIn("7. **Publish**", instructions)
            self.assertIn("## Report publication", instructions)
            self.assertIn('publish_report(report_name="report-v1.md")', instructions)
            self.assertIn('publish_report(report_name="report-v2.md")', instructions)
            self.assertIn("Microsoft Entra", instructions)
            self.assertIn("--auth-mode login", instructions)
            self.assertNotIn("its expiry", instructions)
            self.assertEqual(create.call_args.kwargs["tools"], [*tools, export_tool])
            self.assertIs(create.call_args.kwargs["subagents"][0]["tools"], tools)

    def test_existing_graph_call_remains_valid_and_researcher_tools_are_unchanged(
        self,
    ) -> None:
        model = MagicMock()
        checkpointer = MagicMock()
        tools = [MagicMock()]
        export_tool = MagicMock()
        with patch.object(agent, "create_deep_agent") as create:
            agent.build_agent(model, checkpointer, tools)
            self.assertIs(create.call_args.kwargs["tools"], tools)
            agent.build_agent(model, checkpointer, tools, export_tool)
            self.assertEqual(create.call_args.kwargs["tools"], [*tools, export_tool])
            researcher = create.call_args.kwargs["subagents"][0]
            self.assertIs(researcher["tools"], tools)
            self.assertEqual(agent.MAX_CONCURRENT_RESEARCH_UNITS, 3)
            self.assertEqual(agent.MAX_RESEARCHER_ITERATIONS, 3)


class BlobCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_info_survives_a_full_hosted_console_tail(self) -> None:
        console = io.StringIO()
        root = logging.getLogger()
        core = logging.getLogger("azure.ai.agentserver.core")
        identity = logging.getLogger("azure.identity")
        token = logging.getLogger("azure.identity.aio._internal.get_token_mixin")

        async def run_host(**_kwargs: int) -> None:
            for _ in range(150):
                core.info("Foundry state read succeeded")
                token.info("Managed identity token acquired")
            core.warning("Foundry state read failed")

        with ExitStack() as stack:
            for logger in (root, core, identity, token):
                stack.callback(logger.setLevel, logger.level)
                logger.setLevel(logging.NOTSET)
            stack.enter_context(patch.object(root, "handlers", []))
            stack.enter_context(patch("sys.stderr", console))
            checkpoint = MagicMock()
            checkpoint.__aenter__ = AsyncMock()
            checkpoint.__aexit__ = AsyncMock()
            stack.enter_context(
                patch.object(main, "FoundryCheckpointSaver", return_value=checkpoint)
            )
            for name in (
                "DefaultAzureCredential",
                "build_chat_model",
                "build_agent",
                "create_report_export_tool",
            ):
                stack.enter_context(patch.object(main, name))
            stack.enter_context(
                patch.object(main, "load_tools", new=AsyncMock(return_value=[]))
            )
            host = stack.enter_context(patch.object(main, "ResponsesHostServer"))
            host.return_value.run_async = run_host
            stack.enter_context(patch.dict(os.environ))
            await main.main()

        tail = "\n".join(console.getvalue().splitlines()[-300:])
        startup = "Starting Deep Agents host with Entra-authenticated report downloads"
        self.assertEqual(
            tail.count(startup),
            1,
        )
        self.assertEqual(tail.count("Foundry state read failed"), 1)

    async def test_report_credential_is_scoped_to_host_success_and_failure(
        self,
    ) -> None:
        for name in ("azure.ai.agentserver.core", "azure.identity"):
            logger = logging.getLogger(name)
            self.addCleanup(logger.setLevel, logger.level)
        for failure, content_capture in product((False, True), (None, "false")):
            with self.subTest(failure=failure, content_capture=content_capture):
                credential_scope = MagicMock()
                credential = credential_scope.__enter__.return_value
                checkpoint_scope = MagicMock()
                checkpoint_scope.__aenter__ = AsyncMock()
                checkpoint_scope.__aexit__ = AsyncMock(return_value=False)
                checkpointer = checkpoint_scope.__aenter__.return_value
                tools = [MagicMock()]
                model = MagicMock()
                graph = MagicMock()
                export_tool = MagicMock()
                host = MagicMock()
                host.run_async = AsyncMock(
                    side_effect=RuntimeError("host failed") if failure else None
                )
                with (
                    patch.dict(os.environ, {"PORT": "8091"}),
                    patch.object(main.logging, "basicConfig") as configure_logging,
                    patch.object(
                        main, "DefaultAzureCredential", return_value=credential_scope
                    ),
                    patch.object(
                        main, "FoundryCheckpointSaver", return_value=checkpoint_scope
                    ),
                    patch.object(main, "load_tools", new=AsyncMock(return_value=tools)),
                    patch.object(main, "build_chat_model", return_value=model),
                    patch.object(
                        main, "create_report_export_tool", return_value=export_tool
                    ) as create_export,
                    patch.object(main, "build_agent", return_value=graph) as build,
                    patch.object(
                        main, "ResponsesHostServer", return_value=host
                    ) as main_host,
                ):
                    capture_flags = (
                        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
                        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
                    )
                    for flag in capture_flags:
                        os.environ.pop(flag, None)
                        if content_capture is not None:
                            os.environ[flag] = content_capture
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, "host failed"):
                            await main.main()
                    else:
                        await main.main()
                    configure_logging.assert_called_once_with(level=main.logging.INFO)
                    for flag in capture_flags:
                        expected = content_capture
                        if flag == "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED":
                            expected = content_capture or "true"
                        self.assertEqual(os.environ.get(flag), expected)
                    main_host.assert_called_once_with(graph)
                    create_export.assert_called_once_with(credential)
                    build.assert_called_once_with(
                        model, checkpointer, tools, export_tool
                    )
                    host.run_async.assert_awaited_once_with(port=8091)
                    credential_scope.__exit__.assert_called_once()
                    checkpoint_scope.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
