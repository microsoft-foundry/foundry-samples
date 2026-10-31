# Copyright (c) Microsoft. All rights reserved.
"""Travel constraints, discovered-tool contracts, transport and native HTTP."""

import asyncio
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.request import urlopen

import httpx2 as httpx

RUNTIME = Path(__file__).resolve().parents[1] / "src" / "travel-a2a"
sys.path.insert(0, str(RUNTIME))
from catalogs import (
    FLIGHT_EXAMPLE,
    HOTEL_EXAMPLE,
    choose_itinerary,
    flight_query,
    hotel_query,
    search_flights,
    search_hotels,
    validate_trip,
)
from planner import TravelPlanner, discover_tools, specialist_result, validate_arguments
from services import FoundryServices

PROJECT = "https://example.services.ai.azure.com/api/projects/test"
TOOLBOX = PROJECT + "/toolboxes/travel/versions/1/mcp?api-version=v1"
TRIP = {
    **{key: value for key, value in FLIGHT_EXAMPLE.items() if key != "refundable"},
    "flight_refundable": True,
    "hotel_refundable": True,
    "budget_cents": 120000,
    "max_office_distance_meters": 3000,
}
SELECTION = {
    "status": "proposed",
    "flight_id": "FLIGHT-102",
    "hotel_id": "HOTEL-202",
    "explanation": "Refundable options meet the deadline and office-distance limit.",
}


def tools():
    return {
        "tools": [
            {
                "name": "discovered_" + role,
                "description": role + " catalog",
                "inputSchema": {
                    "type": "object",
                    "required": ["message"],
                    "properties": {
                        "message": {
                            "type": "object",
                            "required": ["parts"],
                            "properties": {
                                "parts": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "kind": {"type": "string"},
                                            "text": {"type": "string"},
                                        },
                                    },
                                }
                            },
                        }
                    },
                },
                "_meta": {
                    "tool_configuration": {
                        "name": config,
                        "type": "a2a",
                        "a2a_version": "1.0",
                    }
                },
            }
            for role, config in [
                ("flights", "flight_options"),
                ("hotels", "hotel_options"),
            ]
        ]
    }


def model_json(value):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            },
        ],
    }


def model_calls(*roles):
    return {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": "discovered_" + role,
                "arguments": "{}",
                "call_id": "call_" + role,
            }
            for role in roles
        ],
    }


def remote_result(role, trip=TRIP):
    payload = (
        search_flights(flight_query(trip))
        if role == "flights"
        else search_hotels(hotel_query(trip))
    )
    payload.update(task_id="remote-" + role, execution_id="execution-" + role)
    return {
        "structuredContent": {
            "id": payload["task_id"],
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [{"parts": [{"text": json.dumps(payload)}]}],
        }
    }


class CatalogTests(unittest.TestCase):
    def test_exact_constraints_and_total(self):
        flights, hotels = search_flights(FLIGHT_EXAMPLE), search_hotels(HOTEL_EXAMPLE)
        self.assertEqual(["FLIGHT-102"], [item["id"] for item in flights["options"]])
        self.assertEqual(
            ["HOTEL-202", "HOTEL-204"], [item["id"] for item in hotels["options"]]
        )
        self.assertEqual(44000, flights["options"][0]["total_cents"])
        self.assertEqual(72500, hotels["options"][0]["total_cents"])
        result = choose_itinerary(
            TRIP, {"flights": flights, "hotels": hotels}, SELECTION
        )
        self.assertEqual(116500, result["total_cents"])
        self.assertEqual(3500, result["remaining_cents"])
        self.assertFalse(result["booking_created"])

    def test_capacity_and_exact_room_pricing(self):
        result = search_hotels({**HOTEL_EXAMPLE, "travelers": 3})
        self.assertEqual(2, result["options"][0]["rooms_needed"])
        self.assertEqual(145000, result["options"][0]["total_cents"])
        result = search_flights({**FLIGHT_EXAMPLE, "travelers": 3})
        self.assertEqual(132000, result["options"][0]["total_cents"])

    def test_budget_boundary_no_match_and_fabrication(self):
        results = {
            "flights": search_flights(FLIGHT_EXAMPLE),
            "hotels": search_hotels(HOTEL_EXAMPLE),
        }
        for budget, status in [
            (116500, "proposed"),
            (116499, "no_match"),
            (90000, "no_match"),
        ]:
            selection = SELECTION if status == "proposed" else {"status": "no_match"}
            self.assertEqual(
                status,
                choose_itinerary({**TRIP, "budget_cents": budget}, results, selection)[
                    "status"
                ],
            )
        with self.assertRaises(ValueError):
            choose_itinerary(TRIP, results, {"status": "no_match"})
        with self.assertRaises(ValueError):
            choose_itinerary(TRIP, results, {**SELECTION, "flight_id": "INVENTED"})
        changed = copy.deepcopy(results)
        changed["flights"]["options"][0]["total_cents"] -= 1000
        with self.assertRaises(ValueError):
            choose_itinerary(TRIP, changed, SELECTION)

    def test_invalid_inputs_and_dates(self):
        cases = [
            {"travelers": True},
            {"travelers": 5},
            {"refundable": "true"},
            {"return_date": "2027-01-09"},
            {"return_date": "2027-02-01"},
            {"arrive_by": "2027-01-11T09:00:00"},
            {"arrive_by": "2027-01-14T09:00:00-08:00"},
            {"origin": "San Francisco"},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                search_flights({**FLIGHT_EXAMPLE, **change})
        for change in [
            {"max_office_distance_meters": True},
            {"max_office_distance_meters": -1},
        ]:
            with self.assertRaises(ValueError):
                search_hotels({**HOTEL_EXAMPLE, **change})
        for budget in [True, -1, 10000001]:
            with self.assertRaises(ValueError):
                validate_trip({**TRIP, "budget_cents": budget})
        self.assertEqual(
            "no_options",
            search_hotels({**HOTEL_EXAMPLE, "destination": "LHR"})["status"],
        )

    def test_discovery_requires_both_correct_tools_and_schema(self):
        self.assertEqual(
            "discovered_flights", discover_tools(tools())["flights"]["name"]
        )
        cases = [[], tools()["tools"][:1], tools()["tools"] * 2]
        for value in cases:
            with self.assertRaises(RuntimeError):
                discover_tools({"tools": value})
        for field, value in [("a2a_version", "0.3"), ("type", "a2a_preview")]:
            bad = tools()
            bad["tools"][0]["_meta"]["tool_configuration"][field] = value
            with self.assertRaises(RuntimeError):
                discover_tools(bad)
        bad = tools()
        bad["tools"][0]["inputSchema"] = {}
        with self.assertRaises(RuntimeError):
            discover_tools(bad)

    def test_task_evidence_completion_and_artifact_checks(self):
        good = remote_result("flights")
        self.assertEqual(
            "remote-flights", specialist_result(good, "flights", TRIP)["task_id"]
        )
        text_only = {
            "content": [{"type": "text", "text": json.dumps(good["structuredContent"])}]
        }
        self.assertEqual(
            "remote-flights", specialist_result(text_only, "flights", TRIP)["task_id"]
        )
        for mutate in ["state", "id", "artifact", "price"]:
            bad = copy.deepcopy(good)
            task = bad["structuredContent"]
            if mutate == "state":
                task["status"]["state"] = "TASK_STATE_WORKING"
            elif mutate == "id":
                task["id"] = "unrelated"
            elif mutate == "artifact":
                task["artifacts"] = []
            else:
                payload = json.loads(task["artifacts"][0]["parts"][0]["text"])
                payload["options"][0]["total_cents"] = 1
                task["artifacts"][0]["parts"][0]["text"] = json.dumps(payload)
            with self.subTest(mutate=mutate), self.assertRaises(
                (RuntimeError, ValueError)
            ):
                specialist_result(bad, "flights", TRIP)

    def test_no_approval_task_reuse_or_query_mutation(self):
        valid = {
            "message": {"parts": [{"kind": "text", "text": json.dumps(FLIGHT_EXAMPLE)}]}
        }
        validate_arguments(valid, FLIGHT_EXAMPLE)
        bad_queries = [
            {"message": {"taskId": "existing", "parts": valid["message"]["parts"]}},
            {"message": {"parts": [{"kind": "data", "data": {"approve": True}}]}},
            {
                "message": {
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps({**FLIGHT_EXAMPLE, "travelers": True}),
                        }
                    ]
                }
            },
        ]
        for bad in bad_queries:
            with self.assertRaises(ValueError):
                validate_arguments(bad, FLIGHT_EXAMPLE)


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planner = TravelPlanner(PROJECT, "model", TOOLBOX)
        self.services = self.planner.services
        self.services.model_response = AsyncMock(
            side_effect=[
                model_json({"requirements": TRIP, "question": ""}),
                model_calls("flights", "hotels"),
                model_json(SELECTION),
            ]
        )
        self.services.rpc = AsyncMock(
            side_effect=[tools(), remote_result("flights"), remote_result("hotels")]
        )

    async def asyncTearDown(self):
        await self.planner.close()

    async def test_llm_uses_discovered_names_and_both_remote_results(self):
        result = await self.planner.plan("Synthetic test request")
        self.assertTrue(result["toolbox_verified"])
        self.assertEqual("1165.00", result["total_usd"])
        self.assertEqual(
            {"flights", "hotels"}, {item["role"] for item in result["delegations"]}
        )
        calls = self.services.rpc.call_args_list
        self.assertEqual("tools/list", calls[0].args[0])
        self.assertEqual("discovered_flights", calls[1].args[1]["name"])
        self.assertEqual("discovered_hotels", calls[2].args[1]["name"])
        validate_arguments(calls[1].args[1]["arguments"], FLIGHT_EXAMPLE)
        validate_arguments(calls[2].args[1]["arguments"], HOTEL_EXAMPLE)
        self.assertEqual(3, self.services.model_response.await_count)

    async def test_missing_requirements_do_not_call_any_tool(self):
        incomplete = {**TRIP, "departure_date": None, "return_date": None}
        self.services.model_response.side_effect = [
            model_json(
                {
                    "requirements": incomplete,
                    "question": "What are your departure and return dates?",
                }
            )
        ]
        result = await self.planner.plan("I need to travel")
        self.assertEqual("needs_clarification", result["status"])
        self.assertFalse(result["toolbox_verified"])
        self.services.rpc.assert_not_awaited()

    async def test_no_match_still_requires_both_tools(self):
        self.services.model_response.side_effect = [
            model_json(
                {"requirements": {**TRIP, "budget_cents": 90000}, "question": ""}
            ),
            model_calls("flights", "hotels"),
            model_json(
                {**SELECTION, "status": "no_match", "flight_id": None, "hotel_id": None}
            ),
        ]
        result = await self.planner.plan("Budget USD 900")
        self.assertEqual("no_match", result["status"])
        self.assertEqual(2, len(result["delegations"]))
        schema = self.services.model_response.call_args.args[0]["text"]["format"][
            "schema"
        ]
        self.assertEqual(["no_match"], schema["properties"]["status"]["enum"])
        self.assertEqual({"type": "null"}, schema["properties"]["flight_id"])
        self.assertEqual({"type": "null"}, schema["properties"]["hotel_id"])

    async def test_tool_failure_never_becomes_model_only_success(self):
        self.services.rpc.side_effect = [tools(), RuntimeError("tool failed")]
        with self.assertRaisesRegex(RuntimeError, "tool failed"):
            await self.planner.plan("Trip")
        self.assertEqual(2, self.services.model_response.await_count)

    async def test_early_final_unknown_and_duplicate_calls_fail(self):
        for answer in [
            model_json(SELECTION),
            model_calls("invented"),
            model_calls("flights", "flights"),
        ]:
            self.services.model_response.side_effect = [
                model_json({"requirements": TRIP, "question": ""}),
                answer,
            ]
            self.services.rpc.side_effect = [tools(), remote_result("flights")]
            with self.subTest(answer=answer), self.assertRaises(RuntimeError):
                await self.planner.plan("Trip")

    async def test_more_expensive_model_selection_is_rejected(self):
        # Relax refundable requirements so two eligible combinations fit this budget.
        trip = {
            **TRIP,
            "flight_refundable": False,
            "hotel_refundable": False,
            "budget_cents": 200000,
        }
        self.services.model_response.side_effect = [
            model_json({"requirements": trip, "question": ""}),
            model_calls("flights", "hotels"),
            model_json({**SELECTION, "hotel_id": "HOTEL-204"}),
        ]
        self.services.rpc.side_effect = [
            tools(),
            remote_result("flights", trip),
            remote_result("hotels", trip),
        ]
        with self.assertRaisesRegex(ValueError, "cheapest"):
            await self.planner.plan("Trip")


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_and_sse_and_http200_errors(self):
        for mode in [
            "json",
            "sse",
            "rpc_error",
            "tool_error",
            "missing",
            "wrong_id",
            "html",
        ]:
            service = FoundryServices(PROJECT, "model", TOOLBOX)
            service.headers = AsyncMock(return_value={"Authorization": "test-token"})
            await service.http.aclose()

            def respond(request, mode=mode):
                body = json.loads(request.content)
                self.assertEqual(TOOLBOX, str(request.url))
                value = {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}}
                if mode == "rpc_error":
                    value = {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": -1, "message": "failed"},
                    }
                elif mode == "tool_error":
                    value["result"] = {"isError": True}
                elif mode == "missing":
                    del value["result"]
                elif mode == "wrong_id":
                    value["id"] = "another-call"
                if mode == "sse":
                    return httpx.Response(
                        200,
                        text="event: message\ndata: " + json.dumps(value) + "\n\n",
                        headers={"content-type": "text/event-stream"},
                    )
                if mode == "html":
                    return httpx.Response(
                        200, text="OK", headers={"content-type": "text/html"}
                    )
                return httpx.Response(200, json=value)

            service.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            try:
                if mode in {"json", "sse"}:
                    self.assertEqual({"tools": []}, await service.rpc("tools/list", {}))
                else:
                    with self.assertRaises(RuntimeError):
                        await service.rpc("tools/list", {})
            finally:
                await service.close()

    async def test_model_incomplete_empty_and_http_error(self):
        for value in [{"status": "incomplete", "output": []}, {"status": "completed"}]:
            service = FoundryServices(PROJECT, "model", TOOLBOX)
            service.headers = AsyncMock(return_value={})
            await service.http.aclose()
            service.http = httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request, value=value: httpx.Response(200, json=value)
                )
            )
            try:
                with self.assertRaises((RuntimeError, TypeError)):
                    await service.model_response({"input": "test"})
            finally:
                await service.close()

    async def test_only_same_project_https_toolbox_is_trusted(self):
        for endpoint in [
            TOOLBOX.replace("example.", "attacker."),
            TOOLBOX.replace("https:", "http:"),
            PROJECT + "/toolboxes/../agents/evil/mcp?api-version=v1",
            TOOLBOX + "#fragment",
            TOOLBOX.replace("/projects/test/", "/projects/other/"),
        ]:
            with self.assertRaises(ValueError):
                FoundryServices(PROJECT, "model", endpoint)


class NativeHTTPTests(unittest.TestCase):
    def test_native_flight_and_hotel_tasks(self):
        for role, query in [("flights", FLIGHT_EXAMPLE), ("hotels", HOTEL_EXAMPLE)]:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            with tempfile.TemporaryFile(mode="w+") as log:
                env = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith("FOUNDRY_")
                }
                env.update(AGENT_ROLE=role, PORT=str(port), PYTHONPATH=str(RUNTIME))
                process = subprocess.Popen(
                    [sys.executable, str(RUNTIME / "main.py")],
                    cwd=RUNTIME,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 40
                    while True:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            self.fail(log.read())
                        try:
                            with urlopen(
                                f"http://127.0.0.1:{port}/readiness", timeout=1
                            ) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            time.sleep(0.05)

                    async def invoke(port=port, query=query, role=role):
                        async with httpx.AsyncClient(timeout=30) as client:
                            response = await client.post(
                                f"http://127.0.0.1:{port}/a2a",
                                headers={"A2A-Version": "1.0"},
                                json={
                                    "jsonrpc": "2.0",
                                    "id": "native-test",
                                    "method": "SendMessage",
                                    "params": {
                                        "message": {
                                            "messageId": "test-message",
                                            "role": "ROLE_USER",
                                            "parts": [{"text": json.dumps(query)}],
                                        },
                                        "configuration": {"returnImmediately": False},
                                    },
                                },
                            )
                            response.raise_for_status()
                            value = response.json()
                            self.assertNotIn("error", value)
                            task = value["result"]["task"]
                            parsed = specialist_result(
                                {"structuredContent": task}, role, TRIP
                            )
                            stored = await client.post(
                                f"http://127.0.0.1:{port}/a2a",
                                headers={"A2A-Version": "1.0"},
                                json={
                                    "jsonrpc": "2.0",
                                    "id": "get-test",
                                    "method": "GetTask",
                                    "params": {"id": task["id"]},
                                },
                            )
                            stored.raise_for_status()
                            self.assertEqual(task["id"], stored.json()["result"]["id"])
                            self.assertTrue(parsed["execution_id"])

                    asyncio.run(invoke())
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
