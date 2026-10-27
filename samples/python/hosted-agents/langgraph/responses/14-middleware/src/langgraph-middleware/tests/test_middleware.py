"""Credential-free acceptance tests using the real middleware and Responses host."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

import pytest
from agent import build_agent
from client import INTERRUPT_NAME, build_resume_items, create_response
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from main import _configure_tracing
from openai import OpenAI
from pydantic import Field
from starlette.testclient import TestClient

EMAIL_ARGS = {
    "recipient": "alice@example.com",
    "subject": "Project update",
    "body": "The review starts at 10:00.",
}


class EmailModel(BaseChatModel):
    """Deterministic stand-in for the external model service."""

    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "test-email-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> EmailModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        if isinstance(messages[-1], ToolMessage):
            reply = AIMessage(content=str(messages[-1].content))
        else:
            reply = AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_email", "name": "send_email", "args": EMAIL_ARGS}
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture(autouse=True)
def isolated_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "false")
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")


def post_response(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/responses", json=body)
    assert response.status_code == 200, response.text
    if body.get("stream"):
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
        assert len(terminal) == 1, events
        payload = terminal[0]["response"]
    else:
        payload = response.json()
    assert payload["status"] == "completed", payload
    return payload


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("decision", ["approve", "edit", "reject"])
def test_review_round_trip(
    stream: bool, decision: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="agent")
    model = EmailModel()
    graph = build_agent(model, InMemorySaver())
    host = ResponsesHostServer(graph)
    conversation = {"id": f"conv_{uuid4().hex}"}
    with TestClient(host.app) as client:
        paused = post_response(
            client,
            {
                "input": "Send the email.",
                "conversation": conversation,
                "stream": stream,
            },
        )
        assert "Simulated send_email tool executed" not in caplog.text
        assert len(model.seen) == 1
        reviews = [
            item for item in paused["output"] if item["type"] == "mcp_approval_request"
        ]
        assert len(reviews) == 1
        assert reviews[0]["server_label"] == "langgraph"
        assert reviews[0]["name"] == INTERRUPT_NAME
        review = json.loads(reviews[0]["arguments"])["value"]
        assert review["action_requests"][0]["args"] == EMAIL_ARGS
        assert review["review_configs"][0]["allowed_decisions"] == [
            "approve",
            "edit",
            "reject",
        ]
        replies = build_resume_items(paused, decision, "bob@example.com")
        resumed = post_response(
            client,
            {
                "input": replies,
                "previous_response_id": paused["id"],
                "conversation": conversation,
                "stream": stream,
            },
        )
    assert not any(item["type"] == "mcp_approval_request" for item in resumed["output"])
    assert len(model.seen) == 2
    tool_messages = [
        message for message in model.seen[-1] if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == 1
    if decision == "reject":
        assert tool_messages[0].status == "error"
        assert "Rejected by the reviewer" in tool_messages[0].content
        assert "Simulated send_email tool executed" not in caplog.text
    else:
        recipient = "bob@example.com" if decision == "edit" else "alice@example.com"
        assert (
            f"Simulated email to {recipient}: Project update"
            in tool_messages[0].content
        )
        assert EMAIL_ARGS["body"] in tool_messages[0].content
        assert caplog.text.count("Simulated send_email tool executed") == 1


@pytest.mark.parametrize("count", [49, 50, 51])
def test_message_limit_precedes_model(count: int) -> None:
    model = EmailModel()
    graph = build_agent(model, InMemorySaver())
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content=f"Message {index}") for index in range(count)
            ]
        },
        {"configurable": {"thread_id": uuid4().hex}},
    )
    if count >= 50:
        assert not model.seen
        assert result["messages"][-1].content == "Conversation limit reached."
    else:
        assert len(model.seen) == 1
        assert result["__interrupt__"]


def test_local_checkpoint_survives_reopen(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="agent")

    async def run() -> None:
        config = {"configurable": {"thread_id": uuid4().hex}}
        async with FoundryCheckpointSaver() as checkpointer:
            graph = build_agent(EmailModel(), checkpointer)
            paused = await graph.ainvoke(
                {"messages": [HumanMessage(content="Send the email.")]}, config
            )
        assert paused["__interrupt__"]
        assert "Simulated send_email tool executed" not in caplog.text
        async with FoundryCheckpointSaver() as checkpointer:
            graph = build_agent(EmailModel(), checkpointer)
            resumed = await graph.ainvoke(
                Command(resume={"decisions": [{"type": "approve"}]}), config
            )
        assert not resumed.get("__interrupt__")
        assert "alice@example.com" in resumed["messages"][-1].content
        assert caplog.text.count("Simulated send_email tool executed") == 1

    asyncio.run(run())


@pytest.mark.parametrize("decision", ["approve", "edit", "reject", "unknown"])
def test_missing_review_fails_closed(decision: str) -> None:
    with pytest.raises(ValueError):
        build_resume_items({"output": []}, decision)


def test_tracing_defaults_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [
        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    ]
    for name in names:
        monkeypatch.delenv(name)
    with _configure_tracing(None):
        assert all(os.environ[name] == "false" for name in names)


def test_real_host_traces_do_not_capture_email_content() -> None:
    source = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    for name in (
        "OTEL_SDK_DISABLED",
        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    ):
        environment.pop(name, None)
    environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
    environment["PYTHONPATH"] = os.pathsep.join([str(source), str(source / "tests")])
    script = """
import json
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_middleware import EMAIL_ARGS, EmailModel, test_openai_review_client
from main import _configure_tracing

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
marker = "PRIVATE-EMAIL-CONTENT-24f03c"
EMAIL_ARGS["body"] = marker
with _configure_tracing(None):
    test_openai_review_client(False)
provider.force_flush()
spans = exporter.get_finished_spans()
assert spans, "No real spans were exported"
assert any("send_email" in span.name for span in spans), [span.name for span in spans]
attributes = json.dumps([json.loads(span.to_json()) for span in spans])
assert marker not in attributes, attributes
assert "alice@example.com" not in attributes, attributes
assert "The review starts at 10:00." not in attributes, attributes
provider.shutdown()
print("Real host telemetry redaction verified")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Real host telemetry redaction verified" in result.stdout


@pytest.mark.parametrize("stream", [False, True])
def test_openai_review_client(stream: bool) -> None:
    host = ResponsesHostServer(build_agent(EmailModel(), InMemorySaver()))
    with TestClient(host.app) as transport:
        with OpenAI(
            base_url="http://testserver", api_key="local", http_client=transport
        ) as client:
            paused = create_response(client, input="Send the email.", stream=stream)
            replies = build_resume_items(paused, "approve")
            resumed = create_response(
                client, input=replies, previous_response_id=paused["id"], stream=stream
            )
    assert "alice@example.com" in json.dumps(resumed)
