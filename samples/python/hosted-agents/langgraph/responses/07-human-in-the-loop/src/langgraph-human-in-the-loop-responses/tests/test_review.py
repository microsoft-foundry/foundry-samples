"""Exercise the sample's actual graph and checkpoint store without a model service."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from langchain_azure_ai.agents.hosting import ResponsesHostServer
from main import _build_graph
from starlette.testclient import TestClient


class DraftModel:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="Draft: " + str(messages[1].content))


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.environment = patch.dict(
            os.environ,
            {
                "OTEL_SDK_DISABLED": "true",
                "AGENTSERVER_STATE_ROOT": os.path.join(
                    self.directory.name, "agentserver"
                ),
                "LANGSMITH_TRACING": "false",
                "LANGSMITH_TRACING_V2": "false",
                "LANGCHAIN_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
            },
        )
        self.environment.start()
        self.model = DraftModel()
        self.graph = _build_graph(self.model)
        self.config = {"configurable": {"thread_id": uuid4().hex}}

    async def asyncTearDown(self):
        await self.graph.checkpointer.aclose()
        self.environment.stop()
        os.chdir(self.original_directory)
        self.directory.cleanup()

    async def begin(self, text):
        return await self.graph.ainvoke(
            {"messages": [HumanMessage(content=text)]}, self.config
        )

    async def approve(self):
        return await self.graph.ainvoke(Command(resume={"approved": True}), self.config)

    async def test_only_approval_emits_the_draft(self):
        paused = await self.begin("FIRST-TASK")
        self.assertTrue(paused["__interrupt__"])
        self.assertFalse(
            any(isinstance(message, AIMessage) for message in paused["messages"])
        )
        completed = await self.approve()
        self.assertEqual(completed["messages"][-1].content, paused["draft"])

    async def test_new_task_uses_latest_user_request(self):
        await self.begin("FIRST-TASK")
        await self.approve()
        paused = await self.begin("SECOND-TASK")
        self.assertIn("SECOND-TASK", paused["draft"])
        self.assertNotIn("FIRST-TASK", paused["draft"])

    async def test_revision_history_is_scoped_to_the_current_task(self):
        await self.begin("FIRST-TASK")
        revised = await self.graph.ainvoke(
            Command(resume={"feedback": "FIRST-TASK-REVISION"}), self.config
        )
        self.assertTrue(revised["__interrupt__"])
        self.assertEqual(
            revised["revision_history"][0]["feedback"], "FIRST-TASK-REVISION"
        )
        await self.approve()
        paused = await self.begin("SECOND-TASK")
        self.assertEqual(paused["revision_history"], [])
        self.assertFalse(
            any(
                "FIRST-TASK-REVISION" in str(message.content)
                for message in self.model.calls[-1]
            )
        )

    def post_response(self, client, body):
        response = client.post("/responses", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        if not body.get("stream"):
            return response.json()
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ") and line[6:] != "[DONE]"
        ]
        terminal = [
            event
            for event in events
            if event["type"] in {"response.completed", "response.failed"}
        ]
        self.assertEqual(len(terminal), 1)
        return terminal[0]["response"]

    async def test_responses_review_decisions(self):
        for stream in (False, True):
            for decision in ("approve", "revise", "reject"):
                with self.subTest(stream=stream, decision=decision):
                    host = ResponsesHostServer(self.graph)
                    conversation = {"id": "conv_" + uuid4().hex}
                    with TestClient(host.app) as client:
                        paused = self.post_response(
                            client,
                            {
                                "input": "HOST-TASK",
                                "conversation": conversation,
                                "stream": stream,
                            },
                        )
                        approval = next(
                            item
                            for item in paused["output"]
                            if item["type"] == "mcp_approval_request"
                        )
                        self.assertEqual(paused["status"], "completed")
                        self.assertEqual(approval["server_label"], "langgraph")
                        self.assertEqual(
                            approval["name"], "__hosted_agent_adapter_interrupt__"
                        )
                        if decision == "revise":
                            call = next(
                                item
                                for item in paused["output"]
                                if item["type"] == "function_call"
                            )
                            reply = {
                                "type": "function_call_output",
                                "call_id": call["call_id"],
                                "output": json.dumps(
                                    {
                                        "resume": {
                                            call["call_id"]: {
                                                "feedback": "REVISE-HOST-TASK"
                                            }
                                        }
                                    }
                                ),
                            }
                        else:
                            reply = {
                                "type": "mcp_approval_response",
                                "approval_request_id": approval["id"],
                                "approve": decision == "approve",
                            }
                        resumed = self.post_response(
                            client,
                            {
                                "input": [reply],
                                "previous_response_id": paused["id"],
                                "conversation": conversation,
                                "stream": stream,
                            },
                        )
                        if decision == "reject":
                            self.assertEqual(resumed["status"], "failed")
                            self.assertEqual(
                                resumed["error"]["code"], "interrupt_rejected"
                            )
                        elif decision == "revise":
                            self.assertEqual(resumed["status"], "completed")
                            self.assertTrue(
                                any(
                                    item["type"] == "mcp_approval_request"
                                    for item in resumed["output"]
                                )
                            )
                            self.assertIn(
                                "REVISE-HOST-TASK", self.model.calls[-1][-1].content
                            )
                        else:
                            self.assertEqual(resumed["status"], "completed")
                            self.assertIn("HOST-TASK", json.dumps(resumed["output"]))
                            self.assertFalse(
                                any(
                                    item["type"] == "mcp_approval_request"
                                    for item in resumed["output"]
                                )
                            )
