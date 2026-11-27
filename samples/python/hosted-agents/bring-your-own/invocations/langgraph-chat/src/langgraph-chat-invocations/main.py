# Copyright (c) Microsoft. All rights reserved.

"""Multi-turn chat agent using LangGraph with Azure OpenAI.

Demonstrates how to integrate a LangGraph agent (with tool-calling) into
the Azure AI Agent Hosting invocations protocol.  The graph has two nodes:

  1. **chatbot** — calls Azure OpenAI (with tools bound)
  2. **tools**   — executes any tool calls the model makes

Tracing: All LangGraph node, LLM, and tool spans are auto-traced via
``langchain-azure-ai`` and exported to Application Insights.
  2. **tools**   — executes any tool calls the model makes

A conditional edge routes back to the chatbot after tool execution so the
model can incorporate the tool results.

Conversation state: Uses an in-memory session store keyed by
``agent_session_id``.  In production, replace with durable storage.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT:    Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME:  Model deployment name (default: gpt-4o)

Usage::

    export FOUNDRY_PROJECT_ENDPOINT="https://your-resource.openai.azure.com/api/projects/proj"
    python main.py

    # Turn 1
    curl -N -X POST 'http://localhost:8088/invocations?agent_session_id=s1' \\
        -H 'Content-Type: application/json' \\
        -d '{"message": "What time is it right now?"}'

    # Turn 2 — remembers context
    curl -N -X POST 'http://localhost:8088/invocations?agent_session_id=s1' \\
        -H 'Content-Type: application/json' \\
        -d '{"message": "And what is 42 * 17?"}'
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Annotated

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from azure.identity import DefaultAzureCredential
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessageChunk
from typing_extensions import TypedDict

from azure.ai.agentserver.invocations import InvocationAgentServerHost

logger = logging.getLogger(__name__)

if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.warning(
        "APPLICATIONINSIGHTS_CONNECTION_STRING not set — traces will not be sent to "
        "Application Insights. Set it to enable local telemetry. "
        "(This variable is auto-injected in hosted Foundry containers — do not declare it in agent.manifest.yaml.)"
    )


# ── Azure OpenAI config ─────────────────────────────────────────────
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


# ── Agent server wiring ─────────────────────────────────────────────
app = InvocationAgentServerHost()


# In-memory session store
_sessions: dict[str, list] = {}


@app.invoke_handler
async def handle_invoke(request: Request):
    """Run the LangGraph agent and stream tokens back via SSE."""
    # Accept either a JSON object ({"message": "..."} or {"input": "..."}) or a
    # plain-text body (e.g. sent directly from the Foundry portal chat UI).
    try:
        body = await request.body()
        if not body:
            raise ValueError("empty body")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            user_message = body.decode("utf-8", errors="replace").strip()
        else:
            if isinstance(data, dict):
                user_message = data.get("message") or data.get("input") or ""
            else:
                user_message = body.decode("utf-8", errors="replace").strip()
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("missing message text")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "message": (
                    'Request body must be a non-empty JSON object with a "message" (or "input") '
                    'string, or a plain-text body, e.g. {"message": "What time is it right now?"}'
                ),
            },
        )

    session_id = request.state.session_id
    invocation_id = request.state.invocation_id

    # Retrieve or create session history
    history = _sessions.setdefault(session_id, [])
    history.append(HumanMessage(content=user_message))

    async def event_generator():
        full_text = ""

        # Run graph with full conversation history
        result = await GRAPH.ainvoke({"messages": list(history)})

        # The last message is the AI response
        ai_message = result["messages"][-1]
        # With use_responses_api, content may be a list of content blocks
        # rather than a plain string.
        raw = ai_message.content
        if isinstance(raw, list):
            full_text = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw
            )
        else:
            full_text = raw or ""

        # Stream the response word-by-word for SSE effect
        words = full_text.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            event = {"type": "token", "content": token}
            yield f"data: {json.dumps(event)}\n\n"

        # Save to history
        history.append(ai_message)

        # Send completion event
        turn = len([m for m in history if isinstance(m, HumanMessage)])
        done_event = {
            "type": "done",
            "invocation_id": invocation_id,
            "session_id": session_id,
            "turn": turn,
            "full_text": full_text,
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run()
