# Copyright (c) Microsoft. All rights reserved.

"""Multi-turn chat agent using LangGraph with Azure OpenAI (responses protocol).

Demonstrates how to integrate a LangGraph agent (with tool-calling) into
the Azure AI Agent Hosting responses protocol.  The graph has two nodes:

  1. **chatbot** — calls Azure OpenAI (with tools bound)
  2. **tools**   — executes any tool calls the model makes

Conversation state: This sample does NOT use any in-memory session state.
Conversation context is automatically managed by the platform via
``previous_response_id`` and ``context.get_history()``.

Tracing: All LangGraph node, LLM, and tool spans are auto-traced via
``langchain-azure-ai`` and exported to Application Insights.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT:         Foundry project endpoint (auto-injected by the platform)
    AZURE_AI_MODEL_DEPLOYMENT_NAME:  Model deployment name (default: gpt-4o)

Usage::

    export FOUNDRY_PROJECT_ENDPOINT="https://your-resource.openai.azure.com/"
    python main.py

    # Turn 1
    curl -N -X POST http://localhost:8088/responses \\
        -H "Content-Type: application/json" \\
        -d '{"model": "chat", "input": "What time is it right now?", "stream": true}'

    # Turn 2 — chain via previous_response_id
    curl -N -X POST http://localhost:8088/responses \\
        -H "Content-Type: application/json" \\
        -d '{"model": "chat", "input": "What is 42 * 17?", "previous_response_id": "<ID>", "stream": true}'
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Annotated

from azure.identity import DefaultAzureCredential
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from typing_extensions import TypedDict

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)
# ── Configuration ────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.warning(
        "APPLICATIONINSIGHTS_CONNECTION_STRING not set — traces will not be sent to "
        "Application Insights. Set it to enable local telemetry. "
        "(This variable is auto-injected in hosted Foundry containers — do not declare it in agent.manifest.yaml.)"
    )

FOUNDRY_PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
if not FOUNDRY_PROJECT_ENDPOINT:
    raise EnvironmentError(
        "FOUNDRY_PROJECT_ENDPOINT environment variable is not set. "
        "Set it to your Foundry project endpoint, or use 'azd ai agent run'."
    )

AZURE_AI_MODEL_DEPLOYMENT_NAME = os.environ.get(
    "AZURE_AI_MODEL_DEPLOYMENT_NAME")
if not AZURE_AI_MODEL_DEPLOYMENT_NAME:
    raise EnvironmentError(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set. "
        "Set it to your model deployment name as declared in agent.manifest.yaml."
    )


# ── Tools ────────────────────────────────────────────────────────────
@tool
def get_current_time() -> str:
    """Return the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple math expression and return the result."""
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error: {e}"


TOOLS = [get_current_time, calculator]


# ── LangGraph definition ────────────────────────────────────────────
class State(TypedDict):
    messages: Annotated[list, add_messages]


def _build_graph() -> StateGraph:
    """Build and compile the LangGraph agent graph."""
    llm = AzureAIOpenAIApiChatModel(
        project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
        model=AZURE_AI_MODEL_DEPLOYMENT_NAME,
        streaming=True,
        # LangGraph manages message history instead of the model service.
        store=False,
    )
    llm_with_tools = llm.bind_tools(TOOLS)

    def chatbot(state: State):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    def route_tools(state: State):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(tools=TOOLS))
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", route_tools, {
                                "tools": "tools", END: END})
    graph.add_edge("tools", "chatbot")
    return graph.compile()


GRAPH = _build_graph()


# ── Helpers ──────────────────────────────────────────────────────────
def _history_to_langchain_messages(history: list) -> list:
    """Convert responses-protocol history items to LangChain messages."""
    messages = []
    for item in history:
        for content in item.get("content") or []:
            text = content.get("text")
            if content.get("type") == "output_text" and text:
                messages.append(AIMessage(content=text))
            elif content.get("type") == "input_text" and text:
                messages.append(HumanMessage(content=text))
    return messages


# ── Agent server wiring ─────────────────────────────────────────────
app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20))


@app.response_handler
async def handle_create(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    """Run the LangGraph agent and stream the response."""

    async def run_graph():
        """Fetch history, run the graph, and yield the result."""
        try:
            try:
                history = await context.get_history()
            except Exception:
                history = []
            current_input = await context.get_input_text() or "Hello!"

            lc_messages = _history_to_langchain_messages(history)
            lc_messages.append(HumanMessage(content=current_input))

            result = await GRAPH.ainvoke({"messages": lc_messages})

            # With use_responses_api, content may be a list of content blocks
            # rather than a plain string.
            raw = result["messages"][-1].content
            if isinstance(raw, list):
                yield "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                )
            else:
                yield raw or ""
        except Exception as exc:
            logger.exception("run_graph failed")
            yield f"[ERROR] {type(exc).__name__}: {exc}"

    return TextResponse(context, request, text=run_graph())


if __name__ == "__main__":
    app.run()
