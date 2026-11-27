"""Sample 03 - configuration-driven Invocations API host.

Defines a minimal no-tool ``create_agent`` graph that uses durable Foundry
checkpointing.
The ``langchain_azure_ai.agents.hosting.run`` module loads the graph from
``langgraph.json`` and hosts it with the selected protocol.

Required environment variables (set in `.env` or your shell):

    FOUNDRY_PROJECT_ENDPOINT        e.g. https://<acct>.services.ai.azure.com/api/projects/<proj>
    AZURE_AI_MODEL_DEPLOYMENT_NAME  e.g. gpt-5.4-mini (defaults to "gpt-5.4-mini")
    PORT                            optional, defaults to 8088

Run::

    az login
    cp .env.example .env  # then edit the values
    python -m langchain_azure_ai.agents.hosting.run --protocol invocations

Then in another terminal:

    curl -i -X POST http://127.0.0.1:8088/invocations \
      -H 'Content-Type: application/json' \
      -d '{"message":"My name is Alice."}'
"""
from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME") or "gpt-5.4-mini"
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


def _configure_tracing() -> None:
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        enable_auto_tracing()
    else:
        enable_auto_tracing(auto_configure_azure_monitor=True)


_configure_tracing()
graph = create_agent(
    _build_chat_model(),
    tools=[],
    checkpointer=FoundryCheckpointSaver(user_isolation=True),
)
