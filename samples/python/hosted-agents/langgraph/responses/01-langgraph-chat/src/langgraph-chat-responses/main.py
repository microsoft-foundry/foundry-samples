# Copyright (c) Microsoft. All rights reserved.

"""LangGraph multi-turn chat agent with local tools (Responses protocol).

Exports a LangGraph agent for the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint.

Conversation state is managed server-side by the platform via
`previous_response_id` — no application-side session storage is needed.
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

    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


graph = create_agent(
    _build_chat_model(),
    tools=[get_current_time, calculator],
)
