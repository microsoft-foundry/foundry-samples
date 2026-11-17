# Copyright (c) Microsoft. All rights reserved.

"""LangGraph math-expert agent with incoming A2A (Responses protocol).

Hosts a LangGraph agent built with `langchain.agents.create_agent` on Foundry
over the Responses protocol, using
`langchain_azure_ai.agents.hosting.ResponsesHostServer`.

Incoming A2A is declared in agent.yaml via `agent_endpoint` + `agent_card`, so
`azd deploy` exposes this agent over A2A (in addition to Responses). Other
Foundry agents (e.g. the sibling `a2a-caller`) can then reach it through
Foundry's A2A endpoint. The agent code itself stays a plain Responses agent —
A2A is added declaratively by the platform, not in code.

Conversation state is managed server-side by the platform via
`previous_response_id` — no application-side session storage is needed.
"""

from __future__ import annotations

import os
from typing import Annotated

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel

load_dotenv()


# ── Tools ────────────────────────────────────────────────────────────
@tool
def calculator(
    expression: Annotated[str, "A math expression to evaluate, e.g. '15 * 23'."],
) -> str:
    """Evaluate a simple arithmetic expression and return the result."""
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307
    except Exception as exc:  # noqa: BLE001 - surface the error to the model
        return f"Error: {exc}"


# ── Chat model ───────────────────────────────────────────────────────
def _build_chat_model() -> AzureAIOpenAIApiChatModel:
    return AzureAIOpenAIApiChatModel(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o"),
        # LangGraph manages message history instead of the model service.
        store=False,
    )


_INSTRUCTIONS = (
    "You are a math expert. When the user asks an arithmetic or algebra question, "
    "use the calculator tool to compute the answer carefully, then reply with a "
    "concise numeric result followed by a one-sentence explanation of the steps. "
    "If the question is not math-related, politely say that you only answer math "
    "questions."
)


# ── Entrypoint ───────────────────────────────────────────────────────
def main() -> None:
    graph = create_agent(
        _build_chat_model(),
        tools=[calculator],
        system_prompt=_INSTRUCTIONS,
    )

    port = int(os.environ.get("PORT", "8088"))
    ResponsesHostServer(graph).run(port=port)


if __name__ == "__main__":
    main()
