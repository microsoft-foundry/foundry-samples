"""Exercise the startup factory, stock instrumentation, and real wire exporters."""

from __future__ import annotations

from contextlib import contextmanager
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from unittest.mock import patch
import zlib

from google.protobuf.json_format import MessageToDict
from opentelemetry import _logs, metrics, trace
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest


MARKERS = {
    "prompt": "PRIVATE-REQUEST-4907ea",
    "recipient": "private-recipient-4907ea@example.com",
    "subject": "PRIVATE-SUBJECT-4907ea",
    "body": "PRIVATE-BODY-4907ea",
}


def exercise_tracing(
    report_path: Path, *, stream: bool, external: bool, natural_exit: bool
) -> None:
    from agent import build_agent
    from client import build_resume_items, create_response
    from langgraph.checkpoint.memory import InMemorySaver
    from main import _create_host
    from openai import OpenAI
    from starlette.testclient import TestClient
    from test_middleware import EmailModel

    executions = []
    blocked = []
    original_connect = socket.socket.connect

    def connect(connection, address):
        if isinstance(address, tuple) and address[0] not in {
            "127.0.0.1",
            "::1",
            "localhost",
        }:
            blocked.append(str(address))
            raise OSError("Trace regression forbids non-loopback connections")
        return original_connect(connection, address)

    class ToolRecorder(logging.Handler):
        def emit(self, record):
            if (
                record.name == "agent"
                and record.getMessage() == "Simulated send_email tool executed"
            ):
                executions.append(record.getMessage())

    class ExternalProvider(TracerProvider):
        shutdown_calls = 0

        def shutdown(self):
            self.shutdown_calls += 1
            super().shutdown()

    exporter = InMemorySpanExporter() if external else None
    provider = ExternalProvider(shutdown_on_exit=False) if external else None
    if provider is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    recorder = ToolRecorder()
    logging.getLogger("agent").addHandler(recorder)
    logging.getLogger("agent").setLevel(logging.INFO)
    model = EmailModel(
        email_actions=[
            {name: value for name, value in MARKERS.items() if name != "prompt"}
        ]
    )
    with patch.object(socket.socket, "connect", connect):
        host = _create_host(build_agent(model, InMemorySaver()))
        with TestClient(host.app) as transport:
            with OpenAI(
                base_url="http://testserver", api_key="local", http_client=transport
            ) as client:
                paused = create_response(client, input=MARKERS["prompt"], stream=stream)
                assert not executions
                resumed = create_response(
                    client,
                    input=build_resume_items(paused, "approve"),
                    previous_response_id=paused["id"],
                    stream=stream,
                )
        report = {
            "model_calls": len(model.seen),
            "tool_executions": len(executions),
            "status": resumed["status"],
            "blocked": blocked,
        }
        current = trace.get_tracer_provider()
        if natural_exit:
            with trace.get_tracer("sample-exit-regression").start_as_current_span(
                "process-exit-sentinel"
            ):
                pass
        elif hasattr(current, "force_flush"):
            current.force_flush()
        if provider is not None:
            assert current is provider
            assert provider.shutdown_calls == 0
            report["external_spans"] = [
                json.loads(span.to_json()) for span in exporter.get_finished_spans()
            ]
        if not natural_exit:
            for configured in (
                current,
                metrics.get_meter_provider(),
                _logs.get_logger_provider(),
            ):
                if hasattr(configured, "shutdown"):
                    configured.shutdown()
        assert not blocked, blocked
        report_path.write_text(json.dumps(report), encoding="utf-8")


@contextmanager
def telemetry_receiver():
    records = []
    messages = {
        "/v1/traces": ExportTraceServiceRequest,
        "/v1/logs": ExportLogsServiceRequest,
        "/v1/metrics": ExportMetricsServiceRequest,
    }

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            elif self.headers.get("Content-Encoding") == "deflate":
                body = zlib.decompress(body)
            if self.path in messages:
                message = messages[self.path]()
                message.ParseFromString(body)
                records.append({"path": self.path, "payload": MessageToDict(message)})
                response = b""
                content_type = "application/x-protobuf"
            else:
                payload = json.loads(body)
                records.append({"path": self.path, "payload": payload})
                count = len(payload) if isinstance(payload, list) else 1
                response = json.dumps(
                    {"itemsReceived": count, "itemsAccepted": count, "errors": []}
                ).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("x-ms-qps-subscribed", "false")
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *arguments):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def exported_spans(records):
    spans = []
    for record in records:
        if record["path"] == "/v1/traces":
            for resource in record["payload"].get("resourceSpans", []):
                for scope in resource.get("scopeSpans", []):
                    for span in scope.get("spans", []):
                        spans.append(
                            {
                                "name": span["name"],
                                "attributes": {
                                    attribute["key"]: next(
                                        iter(attribute["value"].values())
                                    )
                                    for attribute in span.get("attributes", [])
                                },
                            }
                        )
        elif record["path"].startswith("/v2"):
            payload = record["payload"]
            for envelope in payload if isinstance(payload, list) else [payload]:
                data = envelope.get("data", {})
                if data.get("baseType") in {"RequestData", "RemoteDependencyData"}:
                    base = data["baseData"]
                    spans.append(
                        {"name": base["name"], "attributes": base.get("properties", {})}
                    )
    return spans


def run_probe(
    tmp_path,
    *,
    backend="otlp",
    capture=None,
    stream=False,
    disabled=False,
    external=False,
    natural_exit=False,
):
    source = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    for name in list(environment):
        if name.startswith(
            ("OTEL_", "AZURE_TRACING_", "APPLICATIONINSIGHTS_", "APPLICATION_INSIGHTS_")
        ) or name in {
            "FOUNDRY_HOSTING_ENVIRONMENT",
            "FOUNDRY_AGENT365_TRACING_ENABLED",
            "FOUNDRY_PROJECT_ENDPOINT",
            "AZURE_AI_PROJECT_ENDPOINT",
        }:
            environment.pop(name, None)
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join([str(source), str(source / "tests")]),
            "MICROSOFT_OTEL_SDKSTATS_DISABLED": "true",
            "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL": "true",
            "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    if capture is not None:
        environment["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = str(
            capture
        ).lower()
        environment["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = str(
            capture
        ).lower()
    if disabled:
        environment["OTEL_SDK_DISABLED"] = "true"
    report_path = tmp_path / "trace-report.json"
    with telemetry_receiver() as (endpoint, records):
        if backend == "azure-monitor":
            environment["APPLICATIONINSIGHTS_CONNECTION_STRING"] = (
                f"InstrumentationKey=00000000-0000-0000-0000-000000000001;IngestionEndpoint={endpoint}/;LiveEndpoint={endpoint}/"
            )
        elif backend == "otlp-traces":
            environment["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = endpoint + "/v1/traces"
            environment["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = endpoint + "/v1/logs"
            environment["OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"] = (
                endpoint + "/v1/metrics"
            )
        else:
            environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(report_path),
                str(stream).lower(),
                str(external).lower(),
                str(natural_exit).lower(),
            ],
            env=environment,
            text=True,
            capture_output=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["model_calls"] == 2
    assert report["tool_executions"] == 1
    assert report["status"] == "completed"
    assert not report["blocked"]
    return report, records


@pytest.mark.parametrize("backend", ["otlp", "azure-monitor"])
@pytest.mark.parametrize("capture", [None, False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_fresh_host_has_one_instrumentation_owner(
    tmp_path: Path, backend, capture, stream
) -> None:
    report, records = run_probe(
        tmp_path, backend=backend, capture=capture, stream=stream
    )
    spans = exported_spans(records)
    assert sum(span["name"] == "chat" for span in spans) == report["model_calls"], spans
    assert (
        sum(span["name"] == "execute_tool send_email" for span in spans)
        == report["tool_executions"]
    ), spans
    assert any(
        str(span["attributes"].get("microsoft.foundry")).lower() == "true"
        for span in spans
    ), spans
    payload = json.dumps(records)
    for marker in MARKERS.values():
        assert (marker in payload) == (capture is True), records


def test_signal_specific_endpoints_use_stock_exporters(tmp_path: Path) -> None:
    report, records = run_probe(tmp_path, backend="otlp-traces")
    assert (
        sum(span["name"] == "chat" for span in exported_spans(records))
        == report["model_calls"]
    )


def test_disabled_host_does_not_export_telemetry(tmp_path: Path) -> None:
    report, records = run_probe(tmp_path, disabled=True)
    assert report["tool_executions"] == 1
    assert records == []


def test_existing_provider_is_preserved_and_not_closed_by_host(tmp_path: Path) -> None:
    report, records = run_probe(tmp_path, external=True)
    spans = report["external_spans"]
    assert sum(span["name"] == "chat" for span in spans) == 2
    assert sum(span["name"] == "execute_tool send_email" for span in spans) == 1


@pytest.mark.parametrize("backend", ["otlp", "azure-monitor"])
def test_process_exit_flushes_sdk_owned_provider(tmp_path: Path, backend) -> None:
    report, records = run_probe(tmp_path, backend=backend, natural_exit=True)
    spans = exported_spans(records)
    assert sum(span["name"] == "chat" for span in spans) == report["model_calls"]
    assert (
        sum(span["name"] == "execute_tool send_email" for span in spans)
        == report["tool_executions"]
    )
    assert any(span["name"] == "process-exit-sentinel" for span in spans)


if __name__ == "__main__":
    exercise_tracing(
        Path(sys.argv[1]),
        stream=sys.argv[2] == "true",
        external=sys.argv[3] == "true",
        natural_exit=sys.argv[4] == "true",
    )
