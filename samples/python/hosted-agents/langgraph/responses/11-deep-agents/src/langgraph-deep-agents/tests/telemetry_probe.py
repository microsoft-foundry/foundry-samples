"""Verify stock-host telemetry in a fresh process without cloud exporters."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver
from langchain_openai import ChatOpenAI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as sample


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def tool_call(name: str, arguments: dict[str, str]) -> dict:
    return {
        "type": "function_call",
        "id": f"fc_{name}",
        "call_id": f"call_{name}",
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


async def main() -> None:
    markers = {
        "user": "SYNTHETIC-USER-MESSAGE-8241",
        "model": "SYNTHETIC-MODEL-REPLY-2418",
        "tool_input": "SYNTHETIC-REPORT-BODY-6137",
        "tool_output": "https://reports.blob.core.windows.net/reports/snapshot/report-v1.md",
    }
    outputs = [
        tool_call(
            "write_file",
            {"file_path": "/report-v1.md", "content": markers["tool_input"]},
        ),
        tool_call("publish_report", {"report_name": "report-v1.md"}),
        {
            "type": "message",
            "id": "msg_final",
            "role": "assistant",
            "status": "completed",
            "content": [
                {"type": "output_text", "text": markers["model"], "annotations": []}
            ],
        },
    ]
    model_requests = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal model_requests
        assert request.method == "POST" and request.url.path.endswith("/responses")
        output = outputs[model_requests]
        model_requests += 1
        return httpx.Response(
            200,
            json={
                "id": f"resp_{model_requests}",
                "object": "response",
                "created_at": 0,
                "model": "gpt-4o",
                "status": "completed",
                "output": [output],
            },
        )

    async def invoke(host: sample.ResponsesHostServer, *, port: int) -> None:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=host.app), base_url="http://host.test"
            ) as client,
        ):
            result = await client.post(
                "/responses", json={"stream": False, "input": markers["user"]}
            )
            result.raise_for_status()
            assert result.json()["status"] == "completed", result.text
            assert markers["model"] in result.text

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    storage = MagicMock()
    storage.__enter__.return_value = storage
    storage.account_name = "reports"
    storage.get_container_client.return_value.get_container_properties.return_value.public_access = None
    storage.get_blob_client.return_value.url = markers["tool_output"]
    model_transport = httpx.MockTransport(respond)
    project = MagicMock()
    project.get_openai_client.return_value.base_url = "https://model.test/openai/v1/"
    handler = Capture()
    logging.getLogger().addHandler(handler)
    with (
        TemporaryDirectory() as directory,
        httpx.Client(transport=model_transport) as sync_model_client,
        patch.dict(
            os.environ,
            {
                "AGENTSERVER_STATE_ROOT": directory,
                "FOUNDRY_PROJECT_ENDPOINT": "https://project.test",
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-4o",
                "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                "REPORT_STORAGE_CONTAINER": "reports",
            },
        ),
        patch("report_export.BlobServiceClient", return_value=storage),
        patch("utils.AIProjectClient", return_value=project),
        patch("utils.get_bearer_token_provider", return_value=lambda: "mock-token"),
        patch.object(
            sample, "FoundryCheckpointSaver", return_value=FoundryCheckpointSaver(MagicMock())
        ),
        patch.object(sample, "load_tools", new=AsyncMock(return_value=[])),
        patch.object(sample.ResponsesHostServer, "run_async", invoke),
    ):
        async with httpx.AsyncClient(transport=model_transport) as async_model_client:
            with patch(
                "utils.ChatOpenAI",
                partial(
                    ChatOpenAI,
                    http_client=sync_model_client,
                    http_async_client=async_model_client,
                    disable_streaming=True,
                ),
            ):
                await sample.main()
    logging.getLogger().removeHandler(handler)
    logs = "\n".join(handler.messages)
    assert all(marker not in logs for marker in markers.values())
    provider.force_flush()
    spans = exporter.get_finished_spans()
    material = "\n".join(span.to_json() for span in spans)
    print(
        json.dumps(
            {
                "model_requests": model_requests,
                "chat_spans": sum(span.name.startswith("chat ") for span in spans),
                "tool_spans": sorted(
                    span.name.removeprefix("execute_tool ")
                    for span in spans
                    if span.name.startswith("execute_tool ")
                ),
                **{
                    f"{source}_captured": marker in material
                    for source, marker in markers.items()
                },
            }
        )
    )
    provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
