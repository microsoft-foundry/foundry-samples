# Copyright (c) Microsoft. All rights reserved.
"""Failure receipts, terminal Task reporting and retry recovery regressions."""

import importlib.util
import ast
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from a2a.helpers import new_text_message
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard,
    GetTaskRequest,
    ListTasksRequest,
    Role,
    SendMessageRequest,
    TaskState,
)

ROOT = Path(__file__).resolve().parents[1]


def load(name, runtime, filename="main.py"):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "src" / runtime / filename
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FailureTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_card_metadata_matches_manifest(self):
        manifest = (ROOT / "azure.yaml").read_text()
        for runtime in ("travel-agent", "flight-agent", "hotel-agent"):
            tree = ast.parse((ROOT / "src" / runtime / "main.py").read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(
                    node.func, ast.Name
                ):
                    continue
                if node.func.id not in {"AgentCard", "AgentSkill"}:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "description":
                        self.assertIsInstance(keyword.value, ast.Constant)
                        self.assertIn(keyword.value.value, manifest)
                    if keyword.arg == "tags":
                        for tag in ast.literal_eval(keyword.value):
                            self.assertIn(tag, manifest)

    async def test_failed_task_send_list_get_roundtrip_with_real_sdk(self):
        for runtime, executor in (
            ("flight-agent", "FlightExecutor"),
            ("hotel-agent", "HotelExecutor"),
            ("travel-agent", "TravelExecutor"),
        ):
            with self.subTest(runtime=runtime):
                client = ModuleType("client")
                client.ask = AsyncMock(side_effect=TimeoutError("Research timed out"))
                with patch.dict(sys.modules, {"client": client}):
                    module = load("roundtrip_" + runtime, runtime)
                handler = DefaultRequestHandler(
                    getattr(module, executor)(),
                    InMemoryTaskStore(),
                    AgentCard(name="Test", version="1.0.0"),
                )
                context = ServerCallContext()
                sent = await handler.on_message_send(
                    SendMessageRequest(
                        message=new_text_message("Public trip", role=Role.ROLE_USER)
                    ),
                    context,
                )
                self.assertEqual(sent.status.state, TaskState.TASK_STATE_FAILED)
                self.assertTrue(sent.id)
                got = await handler.on_get_task(GetTaskRequest(id=sent.id), context)
                listed = await handler.on_list_tasks(ListTasksRequest(), context)
                self.assertEqual(got.id, sent.id)
                self.assertEqual(got.status.state, TaskState.TASK_STATE_FAILED)
                self.assertIn(sent.id, [task.id for task in listed.tasks])

    async def test_all_executors_report_failure_without_reraising(self):
        for runtime, executor in (
            ("flight-agent", "FlightExecutor"),
            ("hotel-agent", "HotelExecutor"),
            ("travel-agent", "TravelExecutor"),
        ):
            with self.subTest(runtime=runtime):
                client = ModuleType("client")

                async def fail(*args, **kwargs):
                    if "evidence" in kwargs:
                        kwargs["evidence"]["state_store"]["operations"].append(
                            {
                                "action": "created",
                                "plan": {
                                    "plan_id": "plan-" + "a" * 32,
                                    "version": 1,
                                    "requirements_revision": 1,
                                    "status": "needs_replan",
                                    "history": [{"action": "created"}],
                                },
                            }
                        )
                        kwargs["evidence"]["specialist_failures"].append(
                            {
                                "tool": "consult_agent_1",
                                "status": "failed",
                                "error_type": "TimeoutError",
                            }
                        )
                    raise TimeoutError("Research timed out")

                client.ask = fail
                with patch.dict(sys.modules, {"client": client}):
                    module = load("failed_" + runtime, runtime)
                updater = SimpleNamespace(
                    start_work=AsyncMock(),
                    add_artifact=AsyncMock(),
                    complete=AsyncMock(),
                    failed=AsyncMock(),
                )
                with patch.object(module, "TaskUpdater", return_value=updater):
                    await getattr(module, executor)().execute(
                        SimpleNamespace(
                            message=new_text_message("Public trip", role=Role.ROLE_USER)
                        ),
                        SimpleNamespace(enqueue_event=AsyncMock()),
                    )
                updater.failed.assert_awaited_once()
                updater.complete.assert_not_awaited()
                if runtime == "travel-agent":
                    artifacts = {
                        call.kwargs.get("name"): call.kwargs["parts"][0].text
                        for call in updater.add_artifact.await_args_list
                    }
                    state = json.loads(artifacts["trip-state"])
                    self.assertEqual(
                        state["operations"][0]["plan"]["status"], "needs_replan"
                    )
                    self.assertEqual(json.loads(artifacts["specialist-calls"]), [])
                    self.assertEqual(
                        json.loads(artifacts["specialist-failures"])[0]["status"],
                        "failed",
                    )

    async def test_successful_retry_clears_only_matching_failure(self):
        module = load("retry_tools", "travel-agent", "tools.py")
        calls, failed_calls = [], []
        failures = ["consult_agent_2"]

        class Specialist:
            attempts = 0

            async def send_message(self, request):
                self.attempts += 1
                if self.attempts == 1:
                    raise TimeoutError("First attempt failed")
                yield SimpleNamespace(
                    HasField=lambda name: name == "task",
                    task=SimpleNamespace(
                        id="successful-task",
                        status=SimpleNamespace(state=TaskState.TASK_STATE_COMPLETED),
                        artifacts=[SimpleNamespace()],
                    ),
                )

        tool = module.build_tools(
            [
                (
                    SimpleNamespace(name="Flight", description="Research", skills=[]),
                    Specialist(),
                )
            ],
            calls,
            failures,
            research_context={"plan_id": "plan-" + "a" * 32, "plan_version": "1"},
            failed_calls=failed_calls,
        )[0]
        invocation = SimpleNamespace(
            arguments={"message": "Public criteria"}, tool_call_id="retry"
        )
        with self.assertRaises(TimeoutError):
            await tool.handler(invocation)
        self.assertEqual(failures, ["consult_agent_2", "consult_agent_1"])
        with patch.object(module, "get_artifact_text", return_value="Cited evidence"):
            await tool.handler(invocation)
        self.assertEqual(failures, ["consult_agent_2"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(failed_calls), 1)
        self.assertNotIn("task_id", failed_calls[0])


if __name__ == "__main__":
    unittest.main()
