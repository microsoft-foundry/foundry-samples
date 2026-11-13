"""Verify stock-host telemetry in a fresh process without cloud exporters."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver
from langchain_core.messages import AIMessage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_workflow import ScriptedModel, call, hosted_client, response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import build_agent
from report_export import create_report_export_tool


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def main() -> None:
    marker = "PRIVATE-REPORT-CONTENT-NOT-FOR-TELEMETRY-6137"
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    storage = MagicMock()
    storage.__enter__.return_value = storage
    storage.account_name = "reports"
    storage.get_container_client.return_value.get_container_properties.return_value.public_access = None
    storage.get_blob_client.return_value.url = (
        "https://reports.blob.core.windows.net/reports/snapshot/report-v1.md"
    )
    with (
        TemporaryDirectory() as directory,
        patch.dict(
            os.environ,
            {
                "AGENTSERVER_STATE_ROOT": directory,
                "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                "REPORT_STORAGE_CONTAINER": "reports",
                "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "false",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
            },
        ),
        patch("report_export.BlobServiceClient", return_value=storage),
    ):
        model = ScriptedModel(
            disable_streaming=True,
            messages=iter(
                [
                    call(
                        "write_file",
                        {"file_path": "/report-v1.md", "content": marker},
                        "save",
                    ),
                    call("publish_report", {"report_name": "report-v1.md"}, "publish"),
                    AIMessage(
                        content="Report available with Microsoft Entra authentication"
                    ),
                ]
            ),
        )
        graph = build_agent(
            model,
            FoundryCheckpointSaver(MagicMock()),
            [],
            create_report_export_tool(MagicMock()),
        )
        with hosted_client(graph) as client:
            handler = Capture()
            logging.getLogger().addHandler(handler)
            try:
                result = response(client, False, input="Publish my private report")
            finally:
                logging.getLogger().removeHandler(handler)
            assert result["status"] == "completed"
        provider.force_flush()
        spans = exporter.get_finished_spans()
        material = json.dumps(
            [
                {
                    "name": span.name,
                    "attributes": dict(span.attributes or {}),
                    "events": [
                        {"name": event.name, "attributes": dict(event.attributes or {})}
                        for event in span.events
                    ],
                }
                for span in spans
            ],
            default=str,
        )
        assert spans, "No spans emitted by stock host"
        assert marker not in material and marker not in "\n".join(handler.messages)
        assert any(
            "Published report report-v1.md" in message for message in handler.messages
        )
        assert sum(span.name.endswith("publish_report") for span in spans) == 1
        print(
            json.dumps(
                {
                    "telemetry_enabled": True,
                    "publication_span_count": 1,
                    "sensitive_content_absent": True,
                }
            )
        )
    provider.shutdown()


if __name__ == "__main__":
    main()
