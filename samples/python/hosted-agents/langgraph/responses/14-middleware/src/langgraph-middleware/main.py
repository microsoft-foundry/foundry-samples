"""Run the native middleware agent with explicit startup resource ownership."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from agent import build_agent
from azure.ai.projects import AIProjectClient
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
from langchain_openai import ChatOpenAI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


@contextmanager
def _configure_tracing(credential: TokenCredential) -> Iterator[None]:
    os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "false")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        yield
        return
    configure_provider = isinstance(
        trace.get_tracer_provider(), trace.ProxyTracerProvider
    )
    provider = None
    try:
        if os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        ):
            if configure_provider:
                provider = TracerProvider()
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
                trace.set_tracer_provider(provider)
            enable_auto_tracing(auto_configure_azure_monitor=False)
        else:
            enable_auto_tracing(
                credential=credential, auto_configure_azure_monitor=configure_provider
            )
        yield
    finally:
        if provider is not None:
            provider.shutdown()


async def main() -> None:
    """Keep credentials, model transports, and checkpoints alive until host exit."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    with DefaultAzureCredential() as credential, _configure_tracing(credential):
        with (
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
            ) as project,
            project.get_openai_client() as endpoint_client,
        ):
            base_url = str(endpoint_client.base_url)
        model = ChatOpenAI(
            model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"),
            base_url=base_url,
            api_key=get_bearer_token_provider(
                credential, "https://ai.azure.com/.default"
            ),
            use_responses_api=True,
            output_version="responses/v1",
        )
        with model.root_client:
            async with (
                model.root_async_client,
                FoundryCheckpointSaver() as checkpointer,
            ):
                graph = build_agent(model, checkpointer)
                await ResponsesHostServer(graph).run_async(
                    port=int(os.environ.get("PORT", "8088"))
                )


if __name__ == "__main__":
    asyncio.run(main())
