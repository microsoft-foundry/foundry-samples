# Copyright (c) Microsoft. All rights reserved.
"""Failure receipts, terminal Task reporting and retry recovery regressions."""

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import AsyncExitStack
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
    Task,
    TaskState,
)
from google.protobuf.json_format import MessageToDict

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
    async def test_real_planner_client_keeps_pending_specialist_codes(self):
        store_module = load("planner_failure_store", "travel-agent", "plan_store.py")
        tools_module = load("planner_failure_tools", "travel-agent", "tools.py")
        agents_module = load("planner_failure_agents", "travel-agent", "agents.py")
        with patch.dict(
            sys.modules,
            {
                "plan_store": store_module,
                "tools": tools_module,
                "agents": agents_module,
            },
        ):
            module = load("planner_failure_client", "travel-agent", "client.py")
        for reply_raises, permanent in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            with self.subTest(reply_raises=reply_raises, permanent=permanent):
                configuration = {}

                class Specialist:
                    async def send_message(self, request):
                        from a2a.types import TaskStatus

                        yield SimpleNamespace(
                            HasField=lambda name: name == "task",
                            task=Task(
                                id="failed-task",
                                status=TaskStatus(
                                    state=TaskState.TASK_STATE_FAILED,
                                    message=new_text_message(
                                        "Retryable model error: rate_limit_exceeded.",
                                        role=Role.ROLE_AGENT,
                                    ),
                                ),
                            ),
                        )

                class Session:
                    async def send_and_wait(
                        self,
                        message,
                        timeout,
                        reply_raises=reply_raises,
                        configuration=configuration,
                    ):
                        try:
                            await configuration["tools"][0].handler(
                                SimpleNamespace(
                                    arguments={"message": "Public trip"},
                                    tool_call_id="failed-call",
                                )
                            )
                        except RuntimeError:
                            if reply_raises:
                                raise
                        return SimpleNamespace(
                            data=SimpleNamespace(content="No research available")
                        )

                    async def disconnect(self):
                        pass

                async def create_session(configuration=configuration, **kwargs):
                    configuration.update(kwargs)
                    return Session()

                def store_tools(*args, permanent=permanent, **kwargs):
                    kwargs["research_context"].update(
                        plan_id="plan-a", plan_version="1"
                    )
                    if permanent:
                        args[3].append("save_plan_recommendation")
                    return []

                credential = AsyncMock()
                credential.__aenter__.return_value = credential
                credential.get_token.return_value = SimpleNamespace(token="offline")
                store = AsyncMock()
                store.__aenter__.return_value = store
                store.get.return_value = SimpleNamespace(user_isolation=True)
                copilot = SimpleNamespace(
                    start=AsyncMock(), stop=AsyncMock(), create_session=create_session
                )
                evidence = {}
                with (
                    patch.dict(
                        os.environ,
                        {
                            "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/demo",
                            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test",
                            "FLIGHT_AGENT_ENDPOINT": "https://example.test/flights",
                            "HOTEL_AGENT_ENDPOINT": "https://example.test/hotels",
                        },
                        clear=True,
                    ),
                    patch.object(
                        module, "DefaultAzureCredential", return_value=credential
                    ),
                    patch.object(module, "CopilotClient", return_value=copilot),
                    patch.object(
                        module,
                        "connect",
                        AsyncMock(
                            return_value=(
                                SimpleNamespace(
                                    name="Flight", description="Research", skills=[]
                                ),
                                Specialist(),
                            )
                        ),
                    ),
                    patch.object(
                        module,
                        "FoundryStateStore",
                        SimpleNamespace(get_or_create=AsyncMock(return_value=store)),
                    ),
                    patch.object(module, "build_store_tools", side_effect=store_tools),
                    patch.object(
                        module,
                        "get_request_context",
                        return_value=SimpleNamespace(
                            platform_headers=dict,
                            user_id=None,
                            call_id=None,
                        ),
                    ),
                    self.assertRaisesRegex(
                        RuntimeError, "Planner tools failed"
                    ) as raised,
                ):
                    await module.ask("Research", "Public trip", evidence=evidence)
                self.assertEqual(
                    "Retryable model error:" in str(raised.exception), not permanent
                )
                self.assertEqual(
                    evidence["specialist_failures"][0]["error_code"],
                    "rate_limit_exceeded",
                )

    async def test_specialist_failures_preserve_safe_codes_through_planner_and_ci(self):
        tools_module = load("failure_chain_tools", "travel-agent", "tools.py")
        store_module = load("failure_chain_store", "travel-agent", "plan_store.py")
        repo = next(
            parent for parent in ROOT.parents if (parent / ".azure-pipelines").is_dir()
        )
        spec = importlib.util.spec_from_file_location(
            "failure_chain_ci",
            repo
            / ".azure-pipelines"
            / "scripts"
            / "hosted-agents"
            / "scripts"
            / "invoke_hosted_agent_a2a.py",
        )
        assert spec and spec.loader
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)
        for runtime, executor in (
            ("flight-agent", "FlightExecutor"),
            ("hotel-agent", "HotelExecutor"),
        ):
            for diagnostic, code in (
                (
                    "Error calling model: Error code: 429 private-diagnostic",
                    "rate_limit_exceeded",
                ),
                (
                    "Error calling model: Error code: 503 private-diagnostic",
                    "server_error",
                ),
                (
                    "The model is currently experiencing high demand that exceeds the maximum usage size allowed during peak load. private-diagnostic",
                    "rate_limit_exceeded",
                ),
                ("No cited search results private-diagnostic", ""),
                ("Invalid credentials private-diagnostic", ""),
            ):
                with self.subTest(runtime=runtime, code=code, diagnostic=diagnostic):
                    client = ModuleType("client")
                    client.ask = AsyncMock(side_effect=RuntimeError(diagnostic))
                    with patch.dict(sys.modules, {"client": client}):
                        specialist = load("failure_chain_" + runtime, runtime)
                    handler = DefaultRequestHandler(
                        getattr(specialist, executor)(),
                        InMemoryTaskStore(),
                        AgentCard(name="Test", version="1.0.0"),
                    )
                    sent = await handler.on_message_send(
                        SendMessageRequest(
                            message=new_text_message("Public trip", role=Role.ROLE_USER)
                        ),
                        ServerCallContext(),
                    )
                    self.assertEqual(sent.status.state, TaskState.TASK_STATE_FAILED)
                    self.assertNotIn("private-diagnostic", str(sent.status.message))
                    if code:
                        self.assertIn(
                            f"Retryable model error: {code}.", str(sent.status.message)
                        )

                    class Specialist:
                        async def send_message(self, request, task=sent):
                            yield SimpleNamespace(
                                task=task, HasField=lambda name: name == "task"
                            )

                    calls, failures, failed_calls = [], [], []
                    tool = tools_module.build_tools(
                        [
                            (
                                SimpleNamespace(
                                    name="Specialist", description="Research", skills=[]
                                ),
                                Specialist(),
                            )
                        ],
                        calls,
                        failures,
                        research_context={"plan_id": "plan-a", "plan_version": "1"},
                        failed_calls=failed_calls,
                    )[0]
                    with self.assertRaises(RuntimeError):
                        await tool.handler(
                            SimpleNamespace(
                                arguments={"message": "Public trip"},
                                tool_call_id="failed-call",
                            )
                        )
                    self.assertEqual(calls, [])
                    self.assertEqual(failed_calls[0].get("error_code", ""), code)
                    message = store_module.failure_message(failures, [], failed_calls)
                    self.assertEqual("Retryable model error:" in message, bool(code))

                    async def planner_failure(
                        *args, failed_calls=failed_calls, message=message, **kwargs
                    ):
                        kwargs["evidence"]["specialist_failures"].extend(failed_calls)
                        raise RuntimeError(message)

                    planner_client = ModuleType("client")
                    planner_client.ask = planner_failure
                    with patch.dict(sys.modules, {"client": planner_client}):
                        planner = load("failure_chain_planner", "travel-agent")
                    planner_handler = DefaultRequestHandler(
                        planner.TravelExecutor(),
                        InMemoryTaskStore(),
                        AgentCard(name="Planner", version="1.0.0"),
                    )
                    planned = await planner_handler.on_message_send(
                        SendMessageRequest(
                            message=new_text_message("Public trip", role=Role.ROLE_USER)
                        ),
                        ServerCallContext(),
                    )
                    self.assertEqual(planned.status.state, TaskState.TASK_STATE_FAILED)
                    with tempfile.TemporaryDirectory() as directory:
                        work = Path(directory)
                        (work / "input.txt").write_text("Public trip")
                        (work / "turn.json").write_text("{}")

                        def transport(arguments, work=work, planned=planned):
                            request = json.loads((work / "req-1.json").read_text())
                            body = {
                                "jsonrpc": "2.0",
                                "id": request["id"],
                                "result": {"task": MessageToDict(planned)},
                            }
                            return subprocess.CompletedProcess(
                                arguments, 0, json.dumps(body), ""
                            )

                        outcome = ci.invoke_turn(
                            1,
                            work / "input.txt",
                            work / "turn.json",
                            work / "evidence",
                            1,
                            environment={
                                "CI_AGENT_SESSION_ID": "test",
                                "FOUNDRY_AGENT_NAME": "planner",
                            },
                            transport=transport,
                            temp_dir=work,
                        )
                        self.assertEqual(outcome["turn_exit"], 1)
                        self.assertEqual(
                            outcome["approval_terminal_error"], not bool(code)
                        )
                        self.assertEqual(
                            (work / "invoke-response-1.txt").read_text(), ""
                        )

    def test_only_current_allowlisted_unresolved_failure_codes_are_retryable(self):
        store = load("failure_codes_store", "travel-agent", "plan_store.py")
        receipts = [{"tool": "one", "error_code": "rate_limit_exceeded"}]
        self.assertIn(
            "Retryable model error:", store.failure_message(["one"], [], receipts)
        )
        self.assertNotIn(
            "Retryable model error:",
            store.failure_message(["one", "two"], [], receipts),
        )
        self.assertNotIn(
            "Retryable model error:", store.failure_message([], [], receipts)
        )
        receipts.append({"tool": "one", "error_type": "ValueError"})
        self.assertNotIn(
            "Retryable model error:", store.failure_message(["one"], [], receipts)
        )
        receipts.append({"tool": "one", "error_code": "untrusted"})
        self.assertNotIn(
            "Retryable model error:", store.failure_message(["one"], [], receipts)
        )

    async def test_pinned_specialist_version_is_sent_on_discovery_and_invocation(self):
        module = load("version_agents", "travel-agent", "agents.py")
        observed = []
        project = "https://example.test/api/projects/demo"
        endpoint = project + "/agents/flight/endpoint/protocols/a2a"
        real_client = module.httpx.AsyncClient

        def transport(request):
            observed.append(request.headers["x-agent-version-override"])
            return module.httpx.Response(200, json={})

        class Resolver:
            def __init__(self, http, base):
                self.http = http

            async def get_agent_card(self, **kwargs):
                await self.http.get(endpoint + "/agentCard/v1.0?api-version=v1")
                from a2a.types import AgentCard, AgentInterface, AgentSkill

                return AgentCard(
                    name="Flight",
                    skills=[AgentSkill(id="flight")],
                    supported_interfaces=[
                        AgentInterface(
                            protocol_binding="JSONRPC",
                            protocol_version="1.0",
                            url=endpoint,
                        )
                    ],
                )

        async def create(card, config):
            await config.httpx_client.post(endpoint)
            return SimpleNamespace(close=AsyncMock())

        with (
            patch.dict(os.environ, {"FOUNDRY_PROJECT_ENDPOINT": project}),
            patch.object(
                module.httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: real_client(
                    **kwargs, transport=module.httpx.MockTransport(transport)
                ),
            ),
            patch.object(module, "A2ACardResolver", Resolver),
            patch.object(module, "create_client", create),
        ):
            async with AsyncExitStack() as stack:
                await module.connect(
                    endpoint,
                    stack,
                    SimpleNamespace(
                        get_token=AsyncMock(return_value=SimpleNamespace(token="test"))
                    ),
                    {},
                    version="3",
                )
        self.assertEqual(observed, ["3", "3"])

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
                    if "receipts" in kwargs:
                        kwargs["receipts"].append(
                            {
                                "tool": "web_search",
                                "success": False,
                                "source_urls": [],
                            }
                        )
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
                if runtime != "travel-agent":
                    artifact = updater.add_artifact.await_args.kwargs
                    self.assertEqual(artifact["name"], "web-search")
                    self.assertFalse(
                        json.loads(artifact["parts"][0].text)[0]["success"]
                    )
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
