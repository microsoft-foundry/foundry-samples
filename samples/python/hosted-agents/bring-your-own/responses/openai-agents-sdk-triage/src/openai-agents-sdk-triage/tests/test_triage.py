# Copyright (c) Microsoft. All rights reserved.

"""Exercise the real SDK runner and MCP subprocess with a scripted model."""

import asyncio
import os
import unittest
from unittest.mock import patch

import mcp.client.stdio
from agents.mcp import MCPServerStdio
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from openai.types.responses import ResponseTextDeltaEvent

import main


async def collect(model, message="Please investigate this case."):
    return "".join(
        [
            chunk
            async for chunk in main._stream_triage(
                [{"role": "user", "content": message}], asyncio.Event(), model=model
            )
        ]
    )


def tool_outputs(call):
    return [
        item["output"]
        for item in call.input
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]


class HistoryTests(unittest.TestCase):
    def test_preserves_message_roles_order_and_text_parts(self):
        history = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "BILL-1042"}],
            },
            {"type": "reasoning", "content": []},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "The renewal matters."}],
            },
        ]
        current = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "How many"},
                    {"type": "input_text", "text": "seats?"},
                ],
            }
        ]

        self.assertEqual(
            main._build_input_items(history, current),
            [
                {"role": "user", "content": "BILL-1042"},
                {"role": "assistant", "content": "The renewal matters."},
                {"role": "user", "content": "How many\nseats?"},
            ],
        )

    def test_rejects_empty_or_non_text_current_input(self):
        with self.assertRaisesRegex(ValueError, "non-empty user"):
            main._build_input_items([], [])
        with self.assertRaisesRegex(ValueError, "Only text"):
            main._build_input_items(
                [],
                [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": "example"}],
                    }
                ],
            )


class TriageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_handoffs_and_mcp_case_and_article_lookups(self):
        scenarios = [
            (
                "BILL-1042",
                "billing",
                "Billing Specialist",
                "transfer_to_billing_specialist",
                "BILL-RENEWAL",
                "next renewal",
            ),
            (
                "TECH-2048",
                "technical",
                "Technical Specialist",
                "transfer_to_technical_specialist",
                "TECH-SSO-CERT",
                "signing certificate",
            ),
        ]
        for case_id, category, specialist, handoff, article_id, expected in scenarios:
            with self.subTest(case_id=case_id):
                model = ScriptedModel(
                    [
                        [function_call("lookup_case", {"case_id": case_id}, call_id="case")],
                        [function_call(handoff, {}, call_id="handoff")],
                        [
                            function_call(
                                "get_knowledge_article",
                                {"article_id": article_id},
                                call_id="article",
                            )
                        ],
                        [assistant_message("The specialist has the requested guidance.")],
                    ]
                )

                with self.assertLogs("support_triage", level="INFO") as logs:
                    answer = await collect(model, f"Help with {case_id}.")

                model.assert_complete()
                self.assertIn("requested guidance", answer)
                self.assertIn(
                    f"support triage handoff: Triage -> {specialist}", "\n".join(logs.output)
                )
                self.assertIn(category, str(tool_outputs(model.calls[1])))
                self.assertIn(article_id, str(tool_outputs(model.calls[1])))
                self.assertIn(expected, str(tool_outputs(model.calls[3])))
                self.assertEqual(
                    {tool.name for tool in model.calls[0].tools}, {"lookup_case"}
                )
                self.assertEqual(
                    {tool.name for tool in model.calls[2].tools},
                    {"get_knowledge_article"},
                )

    async def test_mcp_imports_installed_dependencies_without_site_initialization(self):
        start_process = mcp.client.stdio._create_platform_compatible_process
        child_environments = []

        async def start_without_site_packages(*args, **kwargs):
            kwargs["args"] = ["-S", *kwargs["args"]]
            child_environments.append(kwargs["env"].copy())
            return await start_process(*args, **kwargs)

        model = ScriptedModel(
            [
                [function_call("lookup_case", {"case_id": "BILL-1042"}, call_id="case")],
                [assistant_message("The case was found.")],
            ]
        )
        with (
            patch.dict(os.environ, {"MCP_TEST_PRIVATE_VALUE": "not-for-child"}),
            patch.object(
                mcp.client.stdio,
                "_create_platform_compatible_process",
                start_without_site_packages,
            ),
        ):
            answer = await collect(model, "Find BILL-1042.")

        model.assert_complete()
        self.assertEqual(answer, "The case was found.")
        self.assertIn("BILL-RENEWAL", str(tool_outputs(model.calls[1])))
        self.assertEqual(len(child_environments), 1)
        self.assertNotIn("MCP_TEST_PRIVATE_VALUE", child_environments[0])

    async def test_unknown_case_reaches_model_as_not_found_without_handoff(self):
        model = ScriptedModel(
            [
                [function_call("lookup_case", {"case_id": "MISSING-1"}, call_id="case")],
                [assistant_message("Case not found.")],
            ]
        )

        with self.assertLogs("support_triage", level="INFO") as logs:
            answer = await collect(model, "Find MISSING-1.")

        model.assert_complete()
        self.assertEqual(answer, "Case not found.")
        self.assertIn('"found": false', str(tool_outputs(model.calls[1])))
        self.assertNotIn("handoff:", "\n".join(logs.output))

    async def test_model_failure_propagates_and_closes_mcp(self):
        closed = asyncio.Event()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        with patch.object(main, "MCPServerStdio", TrackingServer):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                await collect(ScriptedModel([RuntimeError("model unavailable")]))

        self.assertTrue(closed.is_set())

    async def test_cancellation_stops_model_and_closes_mcp(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        closed = asyncio.Event()
        cancellation = asyncio.Event()

        async def blocked_model(_call):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        async def run():
            return [
                chunk
                async for chunk in main._stream_triage(
                    [{"role": "user", "content": "Find BILL-1042."}],
                    cancellation,
                    model=ScriptedModel([ModelStep.respond(blocked_model)]),
                )
            ]

        with patch.object(main, "MCPServerStdio", TrackingServer):
            task = asyncio.create_task(run())
            await asyncio.wait_for(entered.wait(), 15)
            cancellation.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 15)

        self.assertTrue(stopped.is_set())
        self.assertTrue(closed.is_set())

    async def test_consumer_task_cancellation_stops_model_and_closes_mcp(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        closed = asyncio.Event()

        async def blocked_model(_call):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        async def run():
            return await collect(ScriptedModel([ModelStep.respond(blocked_model)]))

        with patch.object(main, "MCPServerStdio", TrackingServer):
            task = asyncio.create_task(run())
            await asyncio.wait_for(entered.wait(), 15)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 15)

        self.assertTrue(stopped.is_set())
        self.assertTrue(closed.is_set())

    async def test_cancellation_reaps_mcp_while_consumer_is_paused(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        closed = asyncio.Event()
        cancellation = asyncio.Event()
        processes = []
        start_process = mcp.client.stdio._create_platform_compatible_process

        async def track_process(*args, **kwargs):
            process = await start_process(*args, **kwargs)
            processes.append(process)
            return process

        async def model_stream(_call):
            try:
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    content_index=0,
                    output_index=0,
                    sequence_number=0,
                    item_id="message",
                    delta="Working",
                    logprobs=[],
                )
                entered.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        with (
            patch.object(main, "MCPServerStdio", TrackingServer),
            patch.object(
                mcp.client.stdio, "_create_platform_compatible_process", track_process
            ),
        ):
            stream = main._stream_triage(
                [{"role": "user", "content": "Find BILL-1042."}],
                cancellation,
                model=ScriptedModel([ModelStep.stream(model_stream)]),
            )
            try:
                async with asyncio.timeout(15):
                    self.assertEqual(await asyncio.create_task(anext(stream)), "Working")
                await asyncio.wait_for(entered.wait(), 15)
                cancellation.set()
                await asyncio.wait_for(stopped.wait(), 15)
                await asyncio.wait_for(closed.wait(), 3)
            finally:
                async with asyncio.timeout(15):
                    await asyncio.create_task(stream.aclose())

        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)

    async def test_cancelled_stream_can_resume_in_another_task(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        closed = asyncio.Event()
        cancellation = asyncio.Event()

        async def model_stream(_call):
            try:
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    content_index=0,
                    output_index=0,
                    sequence_number=0,
                    item_id="message",
                    delta="Working",
                    logprobs=[],
                )
                entered.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        with patch.object(main, "MCPServerStdio", TrackingServer):
            stream = main._stream_triage(
                [{"role": "user", "content": "Find BILL-1042."}],
                cancellation,
                model=ScriptedModel([ModelStep.stream(model_stream)]),
            )
            try:
                self.assertEqual(
                    await asyncio.wait_for(asyncio.create_task(anext(stream)), 15),
                    "Working",
                )
                await asyncio.wait_for(entered.wait(), 15)
                cancellation.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.create_task(anext(stream)), 15)
            finally:
                await asyncio.wait_for(asyncio.create_task(stream.aclose()), 15)

        self.assertTrue(stopped.is_set())
        self.assertTrue(closed.is_set())

    async def test_repeated_consumer_cancellation_waits_for_mcp_cleanup(self):
        entered = asyncio.Event()
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()
        closed = asyncio.Event()

        async def blocked_model(_call):
            entered.set()
            await asyncio.Event().wait()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                cleanup_started.set()
                await release_cleanup.wait()
                await super().cleanup()
                closed.set()

        with patch.object(main, "MCPServerStdio", TrackingServer):
            task = asyncio.create_task(
                collect(ScriptedModel([ModelStep.respond(blocked_model)]))
            )
            try:
                await asyncio.wait_for(entered.wait(), 15)
                task.cancel()
                await asyncio.wait_for(cleanup_started.wait(), 15)
                task.cancel()
                release_cleanup.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 15)
            finally:
                release_cleanup.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        self.assertTrue(closed.is_set())

    async def test_closing_stream_stops_model_and_closes_mcp(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()
        closed = asyncio.Event()

        async def model_stream(_call):
            try:
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    content_index=0,
                    output_index=0,
                    sequence_number=0,
                    item_id="message",
                    delta="Working",
                    logprobs=[],
                )
                entered.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()

        class TrackingServer(MCPServerStdio):
            async def cleanup(self):
                await super().cleanup()
                closed.set()

        with patch.object(main, "MCPServerStdio", TrackingServer):
            stream = main._stream_triage(
                [{"role": "user", "content": "Find BILL-1042."}],
                asyncio.Event(),
                model=ScriptedModel([ModelStep.stream(model_stream)]),
            )
            self.assertEqual(await anext(stream), "Working")
            await asyncio.wait_for(entered.wait(), 15)
            async with asyncio.timeout(15):
                await stream.aclose()

        self.assertTrue(stopped.is_set())
        self.assertTrue(closed.is_set())
