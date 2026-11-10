"""Sample 13 - Responses API branching, rewind, and regeneration.

Hosts a checkpointed ``create_agent`` graph with response branching enabled.
Clients select a branch point with ``previous_response_id`` instead of
continuing from the latest checkpoint in the thread.

Required environment variables (set in ``.env`` or your shell):

    FOUNDRY_PROJECT_ENDPOINT        Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME  defaults to "gpt-5.4-mini"
    PORT                            optional, defaults to 8088

Run::

    az login
    cp .env.example .env  # then edit the values
    python main.py

Then in another terminal::

    python client.py
"""

from __future__ import annotations

import asyncio
import os

from azure.ai.agentserver.core import AgentConfig
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
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
    )


async def main() -> None:
    """Start the branching host with a checkpointer for the current environment."""
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        enable_auto_tracing()
    else:
        enable_auto_tracing(auto_configure_azure_monitor=True)

    checkpointer = (
        FoundryCheckpointSaver(user_isolation=False)
        if AgentConfig.from_env().is_hosted
        else MemorySaver()
    )

    graph = create_agent(
        _build_chat_model(),
        system_prompt=(
            "You remember a single integer. Follow requests to set, add to, "
            "or recall it using this conversation's history. "
            "Reply with only the current integer."
        ),
        checkpointer=checkpointer,
    )

    await ResponsesHostServer(graph, enable_response_branching=True).run_async(
        port=int(os.environ.get("PORT", "8088"))
    )


if __name__ == "__main__":
    asyncio.run(main())
