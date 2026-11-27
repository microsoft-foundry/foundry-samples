# Copyright (c) Microsoft. All rights reserved.

"""LangGraph chat agent with OpenTelemetry tracing (Responses protocol).

Exports a LangGraph agent for the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint, with
GenAI span emission enabled via
`langchain_azure_ai.callbacks.tracers.enable_auto_tracing`.

In hosted mode Foundry injects ``APPLICATIONINSIGHTS_CONNECTION_STRING``,
and ``enable_auto_tracing()`` configures the OpenTelemetry
``TracerProvider`` and Azure Monitor exporter itself — driven by
``OTEL_AUTO_CONFIGURE_AZURE_MONITOR=true`` declared in
``agent.manifest.yaml`` / ``agent.yaml`` — so a single call is enough
to emit traces, metrics, and logs into the project's Azure Monitor /
Application Insights workspace. Locally, supply your own
``APPLICATIONINSIGHTS_CONNECTION_STRING`` in ``.env`` to ship telemetry
from your machine.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


# ── Tools ────────────────────────────────────────────────────────────
@tool
def get_current_time() -> str:
    """Return the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculator(
    expression: Annotated[str, "A math expression to evaluate, e.g. '42 * 17'."],
) -> str:
    """Evaluate a simple math expression and return the result."""
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


# ── Chat model ───────────────────────────────────────────────────────
def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    # Route through the Responses API so spans include `gen_ai.response.id`;
    # without it the Foundry Portal trace view renders empty even though
    # the underlying traces reach App Insights.
    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


def create_graph():
    """Configure tracing and create the graph loaded by the hosting entrypoint."""
    # Enable GenAI OpenTelemetry tracing for every LangGraph node, LLM
    # call, and tool invocation. Configuration is driven by environment
    # variables — see this sample's README for the full list.
    enable_auto_tracing()

    return create_agent(
        _build_chat_model(),
        tools=[get_current_time, calculator],
        system_prompt="You are a friendly assistant. Keep your answers brief.",
    )
