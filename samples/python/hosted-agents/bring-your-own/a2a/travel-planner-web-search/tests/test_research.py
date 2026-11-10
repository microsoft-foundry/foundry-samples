# Copyright (c) Microsoft. All rights reserved.
"""Offline regressions; run with the planner runtime's pinned dependencies."""

import asyncio
import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a2a.types import TaskState
from copilot.generated.session_events import (
    ToolExecutionCompleteData,
    ToolExecutionCompleteResult,
    ToolExecutionStartData,
)

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store_module = load(
    "research_plan_store", ROOT / "src" / "travel-agent" / "plan_store.py"
)
with patch.dict(sys.modules, {"plan_store": store_module}):
    delegation = load("research_tools", ROOT / "src" / "travel-agent" / "tools.py")


class MemoryStore:
    def __init__(self):
        self.records = {}
        self.writes = 0

    async def create_item(self, key, value, **kwargs):
        self.records[key] = copy.deepcopy(value)
        return SimpleNamespace(etag=str(value["version"]))

    async def get_item(self, key, **kwargs):
        value = copy.deepcopy(self.records[key])
        return SimpleNamespace(value=value, etag=str(value["version"]))

    async def set_item(self, key, value, *, if_match, **kwargs):
        if if_match != str(self.records[key]["version"]):
            raise store_module.FoundryStoragePreconditionError(
                "Concurrent write", status_code=412
            )
        self.writes += 1
        self.records[key] = copy.deepcopy(value)
        return SimpleNamespace(etag=str(value["version"]))


REQUIREMENTS = {
    "origin": "SFO",
    "destination": "SEA",
    "office_landmark": "Seattle Convention Center Summit",
    "departure_date": "2027-01-10",
    "return_date": "2027-01-13",
    "arrive_by": "2027-01-11T09:00:00-08:00",
    "travelers": 1,
    "flight_refundable": True,
    "hotel_refundable": True,
    "max_office_distance_meters": 3000,
    "budget_cents": 120000,
}


class PlanResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_only_edit_of_existing_draft_does_not_force_research(self):
        self.operations.clear()
        updated = await self.invoke(
            "update_plan",
            plan_id=self.plan["plan_id"],
            expected_version=1,
            metadata_patch={"label": "Pending trip"},
        )
        self.assertEqual(updated["status"], "needs_replan")
        store_module.validate_completion(self.operations, self.calls)
        self.assertFalse(self.operations[0]["requirements_changed"])

    async def test_requirement_edit_still_requires_completed_research(self):
        self.operations.clear()
        await self.invoke(
            "update_plan",
            plan_id=self.plan["plan_id"],
            expected_version=1,
            requirements_patch={"budget_cents": 100000},
        )
        with self.assertRaisesRegex(RuntimeError, "completed refresh"):
            store_module.validate_completion(self.operations, self.calls)

    async def asyncSetUp(self):
        self.store = MemoryStore()
        self.calls = []
        self.operations = []
        self.failures = []
        self.research_context = {}
        self.tools = {
            tool.name: tool
            for tool in store_module.build_tools(
                self.store,
                self.operations,
                self.calls,
                self.failures,
                call_id=None,
                specialist_tools={"consult_agent_1", "consult_agent_2"},
                research_context=self.research_context,
            )
        }
        self.plan = await self.invoke("create_plan", requirements=REQUIREMENTS)

    async def invoke(self, name, **arguments):
        result = await self.tools[name].handler(
            SimpleNamespace(arguments=arguments, tool_call_id=name)
        )
        return json.loads(result.text_result_for_llm)

    def complete(self, plan=None):
        plan = plan or self.plan
        self.calls.extend(
            {
                "tool": f"consult_agent_{index}",
                "agent": name,
                "task_id": f"task-{len(self.calls)}-{index}",
                "answer": "Cited public research",
                "plan_id": plan["plan_id"],
                "plan_version": str(plan["version"]),
            }
            for index, name in ((1, "Flight"), (2, "Hotel"))
        )

    async def save(self, plan):
        return await self.invoke(
            "save_plan_recommendation",
            plan_id=plan["plan_id"],
            expected_version=plan["version"],
            status="unverified",
            recommendation="Exact-date prices unverified; https://example.test/source",
        )

    async def test_late_old_revision_completions_cannot_clear_pending_refresh(self):
        updated = await self.invoke(
            "update_plan",
            plan_id=self.plan["plan_id"],
            expected_version=1,
            requirements_patch={"budget_cents": 110000},
        )
        self.complete(self.plan)
        with self.assertRaisesRegex(ValueError, "Both specialists"):
            await self.save(updated)
        record = self.store.records[self.plan["plan_id"]]
        self.assertEqual(record["status"], "needs_replan")
        self.assertIsNone(record["recommendation"])
        self.assertEqual(self.store.writes, 1)

    async def test_fresh_both_specialists_save_current_version(self):
        self.complete()
        saved = await self.save(self.plan)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["status"], "unverified")
        self.assertEqual(len(saved["recommendation"]["specialist_tasks"]), 2)

    async def test_full_record_and_history_remain_available_without_writes(self):
        self.complete()
        saved = await self.save(self.plan)
        current = await self.invoke("get_plan", plan_id=saved["plan_id"])
        history = await self.invoke("get_plan_history", plan_id=saved["plan_id"])
        self.assertEqual(current["requirements"], REQUIREMENTS)
        self.assertEqual(current["recommendation"], saved["recommendation"])
        self.assertEqual(current["history_count"], 2)
        self.assertEqual(
            history["history"], self.store.records[saved["plan_id"]]["history"]
        )
        self.assertEqual(self.store.writes, 1)

    async def test_one_specialist_is_not_enough_to_save(self):
        self.complete()
        self.calls.pop()
        with self.assertRaisesRegex(ValueError, "Both specialists"):
            await self.save(self.plan)
        self.assertEqual(self.store.writes, 0)

    async def test_other_plan_results_cannot_satisfy_current_plan(self):
        other = await self.invoke("create_plan", requirements=REQUIREMENTS)
        self.complete(self.plan)
        with self.assertRaisesRegex(ValueError, "Both specialists"):
            await self.save(other)

    async def test_extra_current_delegations_are_allowed(self):
        self.complete()
        self.complete()
        saved = await self.save(self.plan)
        self.assertEqual(len(saved["recommendation"]["specialist_tasks"]), 2)
        self.assertEqual(len(self.calls), 4)

    async def test_duplicate_task_ids_are_rejected(self):
        self.complete()
        self.calls[1]["task_id"] = self.calls[0]["task_id"]
        with self.assertRaisesRegex(ValueError, "duplicate Task IDs"):
            await self.save(self.plan)

    async def test_external_version_change_is_rejected(self):
        self.complete()
        self.store.records[self.plan["plan_id"]]["version"] = 2
        with self.assertRaises(store_module.FoundryStoragePreconditionError):
            await self.save(self.plan)
        self.assertEqual(self.store.writes, 0)

    async def test_delegation_captures_binding_before_await_not_at_completion(self):
        launched = [asyncio.Event(), asyncio.Event()]
        release = asyncio.Event()
        requests = []

        class Specialist:
            def __init__(self, index):
                self.index = index

            async def send_message(self, request):
                requests.append(request)
                launched[self.index].set()
                await release.wait()
                task = SimpleNamespace(
                    id=f"delegated-{self.index}",
                    status=SimpleNamespace(state=TaskState.TASK_STATE_COMPLETED),
                    artifacts=[SimpleNamespace()],
                )
                yield SimpleNamespace(task=task, HasField=lambda name: name == "task")

        agents = [
            (
                SimpleNamespace(name=name, description="Public research", skills=[]),
                Specialist(index),
            )
            for index, name in enumerate(("Flight", "Hotel"))
        ]
        tools = delegation.build_tools(
            agents,
            self.calls,
            self.failures,
            research_context=self.research_context,
        )
        with patch.object(
            delegation, "get_artifact_text", return_value="Cited sources"
        ):
            pending = [
                asyncio.create_task(
                    tool.handler(
                        SimpleNamespace(
                            arguments={"message": "Public SFO SEA trip criteria"},
                            tool_call_id=f"delegation-{index}",
                        )
                    )
                )
                for index, tool in enumerate(tools)
            ]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(event.wait() for event in launched)), timeout=5
                )
                updated = await self.invoke(
                    "update_plan",
                    plan_id=self.plan["plan_id"],
                    expected_version=1,
                    requirements_patch={"budget_cents": 110000},
                )
            finally:
                release.set()
                results = await asyncio.gather(*pending)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(call["plan_version"] == "1" for call in self.calls))
        for result in results:
            self.assertEqual(
                set(json.loads(result.text_result_for_llm)),
                {"agent", "task_id", "answer"},
            )
        for request in requests:
            self.assertNotIn(self.plan["plan_id"], str(request))
            self.assertNotIn("plan_version", str(request))
        with self.assertRaisesRegex(ValueError, "Both specialists"):
            await self.save(updated)
        self.complete(updated)
        saved = await self.save(updated)
        self.assertEqual(saved["status"], "unverified")
        self.assertEqual(saved["requirements_revision"], 2)
        self.assertEqual(self.failures, [])

    async def test_delegation_without_active_plan_fails_explicitly(self):
        self.research_context.clear()
        tools = delegation.build_tools(
            [(SimpleNamespace(name="Flight", description="Research", skills=[]), None)],
            self.calls,
            self.failures,
            research_context=self.research_context,
        )
        with self.assertRaisesRegex(ValueError, "Read or create a plan"):
            await tools[0].handler(
                SimpleNamespace(
                    arguments={"message": "Public criteria"}, tool_call_id="no-plan"
                )
            )
        self.assertEqual(self.calls, [])
        self.assertEqual(self.failures, ["consult_agent_1"])

    async def test_metadata_edit_preserves_saved_recommendation(self):
        self.complete()
        saved = await self.save(self.plan)
        updated = await self.invoke(
            "update_plan",
            plan_id=saved["plan_id"],
            expected_version=saved["version"],
            metadata_patch={"label": "Business trip"},
        )
        self.assertEqual(updated["recommendation"], saved["recommendation"])
        self.assertEqual(updated["requirements_revision"], 1)
        self.assertEqual(updated["status"], "unverified")
        self.assertEqual(len(self.calls), 2)


class SearchEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def test_toolbox_path_normalization_cannot_escape_project(self):
        project = "https://example.test/api/projects/demo"
        for runtime in ("flight-agent", "hotel-agent"):
            client = load("boundary_" + runtime, ROOT / "src" / runtime / "client.py")
            for path in (
                "/toolboxes/../../other/toolboxes/web/mcp",
                "/toolboxes/%2e%2e/web/mcp",
                "/toolboxes/./web/mcp",
                "/toolboxes/web\\..\\other/mcp",
                "/toolboxes/%252e%252e/web/mcp",
            ):
                with self.subTest(runtime=runtime, path=path), self.assertRaises(
                    ValueError
                ):
                    client.validate_toolbox_endpoint(
                        project + path + "?api-version=v1", project
                    )
            client.validate_toolbox_endpoint(
                project + "/toolboxes/web/mcp?api-version=v1", project
            )

    async def run_search(self, runtime, results):
        module = load("research_" + runtime, ROOT / "src" / runtime / "client.py")
        configuration = {}

        class Credential:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get_token(self, scope):
                return SimpleNamespace(token="offline-test")

        class Session:
            async def send_and_wait(self, message, timeout):
                for index, (success, content) in enumerate(results):
                    call_id = f"search-{index}"
                    configuration["on_event"](
                        SimpleNamespace(
                            data=ToolExecutionStartData(
                                tool_call_id=call_id,
                                tool_name="travel_web-web_search",
                                mcp_tool_name="web_search",
                            )
                        )
                    )
                    configuration["on_event"](
                        SimpleNamespace(
                            data=ToolExecutionCompleteData(
                                tool_call_id=call_id,
                                success=success,
                                result=ToolExecutionCompleteResult(content=content),
                            )
                        )
                    )
                return SimpleNamespace(data=SimpleNamespace(content="Cited research"))

            async def disconnect(self):
                pass

        class Copilot:
            async def start(self):
                pass

            async def stop(self):
                pass

            async def create_session(self, **kwargs):
                configuration.update(kwargs)
                return Session()

        project = "https://example.test/api/projects/demo"
        with (
            patch.dict(
                module.os.environ,
                {
                    "FOUNDRY_PROJECT_ENDPOINT": project,
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test",
                    "TOOLBOX_ENDPOINT": project + "/toolboxes/web/mcp?api-version=v1",
                },
                clear=True,
            ),
            patch.object(module, "DefaultAzureCredential", return_value=Credential()),
            patch.object(module, "CopilotClient", return_value=Copilot()),
            patch.object(
                module,
                "get_request_context",
                return_value=SimpleNamespace(platform_headers=lambda: {}),
            ),
        ):
            answer, calls = await module.ask("Public research", "SFO SEA")
        limit = configuration["hooks"]["on_pre_tool_use"]
        self.assertEqual(
            [limit({}, {})["permissionDecision"] for _ in range(3)],
            ["allow", "allow", "deny"],
        )
        self.assertEqual(answer, "Cited research")
        self.assertEqual(len(calls), len(results))
        return calls

    async def test_partial_search_evidence_is_usable_in_either_order(self):
        for runtime in ("flight-agent", "hotel-agent"):
            for unusable in ((False, "https://example.test/error"), (True, "No URLs")):
                for results in (
                    [unusable, (True, "https://example.test/source")],
                    [(True, "https://example.test/source"), unusable],
                ):
                    with self.subTest(runtime=runtime, results=results):
                        calls = await self.run_search(runtime, results)
                        self.assertEqual(sum(call["success"] for call in calls), 1)

    async def test_no_usable_search_evidence_is_rejected(self):
        for runtime in ("flight-agent", "hotel-agent"):
            for results in (
                [],
                [(False, "https://example.test/error")],
                [(True, "No URLs")],
                [(False, "Failed"), (True, "No URLs")],
            ):
                with self.subTest(runtime=runtime, results=results):
                    with self.assertRaisesRegex(RuntimeError, "source URLs"):
                        await self.run_search(runtime, results)

    async def test_denied_attempt_receipt_does_not_invalidate_usable_searches(self):
        for runtime in ("flight-agent", "hotel-agent"):
            with self.subTest(runtime=runtime):
                calls = await self.run_search(
                    runtime,
                    [
                        (True, "https://example.test/first"),
                        (True, "https://example.test/second"),
                        (False, "The two-search budget is exhausted"),
                    ],
                )
                self.assertEqual(sum(call["success"] for call in calls), 2)
                self.assertFalse(calls[-1]["success"])


class DelegationAssertionTests(unittest.TestCase):
    def test_fixture_accepts_two_or_more_not_zero_or_one(self):
        fixture = (
            ROOT.parents[5]
            / ".azure-pipelines"
            / "hosted-agent-tests"
            / "python"
            / "bring-your-own"
            / "a2a"
            / "travel-planner-web-search"
            / "test-spec.yml"
        ).read_text()
        pattern = re.search(
            r"""value: ["'](A2A_PLAN_COMPLETED successful_delegations=.*)["']""",
            fixture,
        )
        self.assertIsNotNone(pattern)
        for count in (0, 1, 2, 3, 4, 10, 11, 20, 100):
            with self.subTest(count=count):
                self.assertEqual(
                    bool(
                        re.search(
                            pattern[1],
                            f"A2A_PLAN_COMPLETED successful_delegations={count} elapsed_ms=1",
                        )
                    ),
                    count >= 2,
                )


if __name__ == "__main__":
    unittest.main()
