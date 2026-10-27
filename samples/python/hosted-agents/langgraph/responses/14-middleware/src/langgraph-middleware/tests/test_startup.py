"""Verify real startup resource ownership and isolated tracing configuration."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import os
from pathlib import Path
import subprocess
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver
from langchain_openai import ChatOpenAI
import main as startup
import pytest


@pytest.mark.parametrize("outcome", ["normal", "initialization-error", "cancelled"])
def test_main_closes_owned_resources(
    outcome: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = []
    resources = {}
    original_build_agent = startup.build_agent

    @contextmanager
    def track(resource, name):
        resources[name] = resource
        try:
            with resource as opened:
                events.append(f"{name}:entered")
                yield opened
        finally:
            events.append(f"{name}:exited")

    def open_project(**arguments):
        project = AIProjectClient(**arguments)
        original_openai = project.get_openai_client

        def open_endpoint_client():
            return track(original_openai(), "endpoint")

        monkeypatch.setattr(project, "get_openai_client", open_endpoint_client)
        return track(project, "project")

    def open_model(**arguments):
        model = ChatOpenAI(**arguments)
        resources["model"] = model
        return model

    @asynccontextmanager
    async def open_checkpointer():
        saver = FoundryCheckpointSaver()
        resources["checkpointer"] = saver
        try:
            async with saver:
                events.append("checkpointer:entered")
                yield saver
        finally:
            events.append("checkpointer:exited")

    def build_graph(model, saver):
        if outcome == "initialization-error":
            raise RuntimeError("graph initialization failed")
        return original_build_agent(model, saver)

    async def exercise():
        entered_host = asyncio.Event()

        async def run_host(host, *, port):
            assert port == 8088
            entered_host.set()
            if outcome == "cancelled":
                await asyncio.Future()

        monkeypatch.setattr(startup.ResponsesHostServer, "run_async", run_host)
        if outcome == "cancelled":
            task = asyncio.create_task(startup.main())
            try:
                await asyncio.wait_for(entered_host.wait(), timeout=20)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        elif outcome == "initialization-error":
            with pytest.raises(RuntimeError, match="graph initialization failed"):
                await startup.main()
            assert not entered_host.is_set()
        else:
            await startup.main()
            assert entered_host.is_set()

    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/test",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-deployment")
    monkeypatch.setenv("PORT", "8088")
    monkeypatch.setattr(startup, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        startup,
        "DefaultAzureCredential",
        lambda: track(DefaultAzureCredential(), "credential"),
    )
    monkeypatch.setattr(startup, "AIProjectClient", open_project)
    monkeypatch.setattr(startup, "ChatOpenAI", open_model)
    monkeypatch.setattr(startup, "FoundryCheckpointSaver", open_checkpointer)
    monkeypatch.setattr(startup, "build_agent", build_graph)
    asyncio.run(exercise())
    assert events == [
        "credential:entered",
        "project:entered",
        "endpoint:entered",
        "endpoint:exited",
        "project:exited",
        "checkpointer:entered",
        "checkpointer:exited",
        "credential:exited",
    ]
    assert resources["endpoint"].is_closed()
    assert resources["model"].root_client.is_closed()
    assert resources["model"].root_async_client.is_closed()
    assert not resources["checkpointer"]._owns_credential


@pytest.mark.parametrize(
    "mode",
    [
        "disabled",
        "otlp",
        "otlp-traces",
        "azure-monitor",
        "external",
        "external-otlp",
        "otlp-error",
        "otlp-exporter-error",
    ],
)
def test_tracing_configuration_and_ownership(mode: str) -> None:
    source = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    for name in (
        "OTEL_SDK_DISABLED",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
        "AZURE_AI_PROJECT_ENDPOINT",
        "FOUNDRY_PROJECT_ENDPOINT",
    ):
        environment.pop(name, None)
    environment["PYTHONPATH"] = str(source)
    environment["TEST_TRACING_MODE"] = mode
    environment["APPLICATION_INSIGHTS_CONNECTION_STRING"] = "test-connection-string"
    script = """
import importlib
import os
from azure.identity import DefaultAzureCredential
from langchain_core.callbacks import CallbackManager
from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
import main as startup
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

mode = os.environ["TEST_TRACING_MODE"]
providers = []
monitor_calls = []
exporters = []

class RecordingProvider(TracerProvider):
    def __init__(self):
        super().__init__(shutdown_on_exit=False)
        self.shutdown_calls = 0
        providers.append(self)

    def shutdown(self):
        self.shutdown_calls += 1
        super().shutdown()

def exporter():
    if mode == "otlp-exporter-error":
        raise RuntimeError("exporter initialization failed")
    result = InMemorySpanExporter()
    exporters.append(result)
    return result

def configure_monitor(**arguments):
    monitor_calls.append(arguments)
    provider = RecordingProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter()))
    trace.set_tracer_provider(provider)

startup.TracerProvider = RecordingProvider
startup.OTLPSpanExporter = exporter
tracer_module = importlib.import_module(AzureAIOpenTelemetryTracer.__module__)
tracer_module.configure_azure_monitor = configure_monitor
if mode == "disabled":
    os.environ["OTEL_SDK_DISABLED"] = "true"
if mode.startswith("otlp") or mode == "external-otlp":
    endpoint = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT" if mode == "otlp-traces" else "OTEL_EXPORTER_OTLP_ENDPOINT"
    os.environ[endpoint] = "http://127.0.0.1:4318"
if mode.startswith("external"):
    configure_monitor(connection_string="external-provider")
    monitor_calls.clear()

try:
    with DefaultAzureCredential() as credential, startup._configure_tracing(credential):
        if mode == "otlp-error":
            raise RuntimeError("host failed")
        if mode != "disabled":
            assert any(isinstance(handler, AzureAIOpenTelemetryTracer) for handler in CallbackManager.configure().inheritable_handlers)
            with trace.get_tracer("startup-test").start_as_current_span("startup-check"):
                pass
            trace.get_tracer_provider().force_flush()
except RuntimeError as error:
    assert mode in {"otlp-error", "otlp-exporter-error"}, error
else:
    assert mode not in {"otlp-error", "otlp-exporter-error"}

assert os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] == "false"
assert os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"
assert len(monitor_calls) == (mode == "azure-monitor"), monitor_calls
if mode == "disabled":
    assert not providers
    assert not CallbackManager.configure().inheritable_handlers
else:
    assert len(providers) == 1
    assert trace.get_tracer_provider() is providers[0] or mode == "otlp-exporter-error"
    owned = mode.startswith("otlp")
    assert providers[0].shutdown_calls == owned
    if mode not in {"otlp-error", "otlp-exporter-error"}:
        assert [span.name for span in exporters[0].get_finished_spans()] == ["startup-check"]
    if not owned:
        providers[0].shutdown()
print("Tracing route and ownership verified")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Tracing route and ownership verified" in result.stdout
