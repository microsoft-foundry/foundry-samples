"""Local sample lifecycle regressions using runtime dependencies, not Azure access.

Run from the repository root in the sample's frozen runtime environment:
    python .github/scripts/runtime-tests/test_langgraph_sample_lifecycle.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / (
    "samples/python/hosted-agents/langgraph/responses/07-human-in-the-loop/"
    "src/langgraph-human-in-the-loop-responses/main.py"
)


class LangGraphSampleLifecycleTests(unittest.TestCase):
    def test_revision_then_new_task_isolates_model_context(self) -> None:
        state_root = self.enterContext(tempfile.TemporaryDirectory())
        spec = importlib.util.spec_from_file_location("hitl_sample_lifecycle", SAMPLE)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        model = types.SimpleNamespace(
            ainvoke=AsyncMock(
                side_effect=[
                    AIMessage(content="SEATTLE-DRAFT-ORIGINAL"),
                    AIMessage(content="SEATTLE-DRAFT-REVISED"),
                    AIMessage(content="PARIS-DRAFT"),
                ]
            )
        )
        with (
            patch.dict(sys.modules, {module.__name__: module}),
            patch.dict(
                os.environ,
                {"AGENTSERVER_STATE_ROOT": state_root, "OTEL_SDK_DISABLED": "true"},
            ),
            patch("dotenv.load_dotenv"),
        ):
            spec.loader.exec_module(module)
            with patch.object(
                module, "FoundryCheckpointSaver", return_value=InMemorySaver()
            ):
                graph = module._build_graph(model)
            with TestClient(ResponsesHostServer(graph).app) as client:
                conversation = {"id": "hitl-lifecycle"}

                def post(input_items: object) -> dict:
                    response = client.post(
                        "/responses",
                        json={"conversation": conversation, "input": input_items},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    self.assertEqual(payload["status"], "completed", payload)
                    return payload

                def pending(payload: dict) -> dict:
                    requests = [
                        item
                        for item in payload["output"]
                        if item.get("type") == "mcp_approval_request"
                    ]
                    self.assertEqual(len(requests), 1, payload)
                    return requests[0]

                def approve(payload: dict) -> dict:
                    return post(
                        [
                            {
                                "type": "mcp_approval_response",
                                "approval_request_id": pending(payload)["id"],
                                "approve": True,
                            }
                        ]
                    )

                def assistant_text(payload: dict) -> str:
                    return "".join(
                        part.get("text", "")
                        for item in payload["output"]
                        if item.get("type") == "message"
                        for part in item.get("content", [])
                    )

                initial = post("Draft a Seattle launch email.")
                pending(initial)
                original_call = model.ainvoke.await_args_list[0]
                self.assertEqual(
                    original_call.args[0][1].content, "Draft a Seattle launch email."
                )
                sentinels = [
                    item
                    for item in initial["output"]
                    if item.get("type") == "function_call"
                    and item.get("name") == "__hosted_agent_adapter_interrupt__"
                ]
                self.assertEqual(len(sentinels), 1, initial)
                feedback = "Keep the Seattle launch date, but shorten the email."
                revised = post(
                    [
                        {
                            "type": "function_call_output",
                            "call_id": sentinels[0]["call_id"],
                            "output": json.dumps({"resume": {"feedback": feedback}}),
                        }
                    ]
                )
                self.assertEqual(
                    json.loads(pending(revised)["arguments"])["value"]["draft"],
                    "SEATTLE-DRAFT-REVISED",
                )
                self.assertEqual(model.ainvoke.await_count, 2)
                revision_messages = model.ainvoke.await_args_list[1].args[0]
                self.assertEqual(
                    [message.content for message in revision_messages[1:]],
                    [
                        "Draft a Seattle launch email.",
                        "SEATTLE-DRAFT-ORIGINAL",
                        f"Revision feedback: {feedback}",
                    ],
                    "revision must apply the current draft and feedback",
                )
                self.assertIsInstance(revision_messages[2], AIMessage)
                self.assertIsInstance(revision_messages[3], HumanMessage)
                approved = approve(revised)
                self.assertFalse(
                    any(
                        item.get("type") == "mcp_approval_request"
                        for item in approved["output"]
                    ),
                    approved,
                )
                self.assertEqual(model.ainvoke.await_count, 2)
                self.assertEqual(assistant_text(approved), "SEATTLE-DRAFT-REVISED")

                following = post("Draft a Paris event invitation.")
                self.assertEqual(model.ainvoke.await_count, 3)
                following_messages = model.ainvoke.await_args_list[2].args[0]
                self.assertEqual(
                    [message.content for message in following_messages[1:]],
                    ["Draft a Paris event invitation."],
                    "new task must exclude the previous draft and revision feedback",
                )
                self.assertEqual(
                    json.loads(pending(following)["arguments"])["value"]["draft"],
                    "PARIS-DRAFT",
                )
                final = approve(following)
                self.assertEqual(model.ainvoke.await_count, 3)
                self.assertEqual(assistant_text(final), "PARIS-DRAFT")
                self.assertFalse(
                    any(
                        item.get("type") == "mcp_approval_request"
                        for item in final["output"]
                    ),
                    final,
                )


if __name__ == "__main__":
    unittest.main()
