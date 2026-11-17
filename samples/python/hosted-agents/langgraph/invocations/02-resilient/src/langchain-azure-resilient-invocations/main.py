"""Resilient background Invocations with a LangGraph agent.

This sample demonstrates the resilient background Invocations feature and how
it composes with LangGraph's own native checkpointer.

The agent uses a real Foundry model and local trip-planning and
crash-simulation tools.

Graph shape::

    START -> model -> [tools -> model] -> END

Optional environment variables:

    PORT               optional, defaults to 8088
    STEERABLE_CONVERSATIONS optional boolean (default false) controlling
                            whether newer turns can steer active conversations.
    FOUNDRY_PROJECT_ENDPOINT required project endpoint for the model.
    AZURE_AI_MODEL_DEPLOYMENT_NAME required model deployment name.

``FoundryCheckpointSaver`` persists LangGraph checkpoints in Foundry State Store
when hosted and automatically uses a local file-backed store otherwise.

Run::

    python main.py

Then in another terminal::

    curl -X POST \
        'http://127.0.0.1:8088/invocations?agent_session_id=trip-demo' \
        -H 'Content-Type: application/json' \
        -d '{"message":"Plan a two-night trip to Seattle.","background":true}'

Poll ``GET /invocations/{invocation_id}`` for completion. Ask the agent to call
``simulate_crash``, then restart the local host or let Foundry restart the
hosted process to watch recovery resume from the pending tool call at the last
checkpoint. Pending LangGraph interrupts are returned as Responses-style HITL
output items and resumed with matching structured items in the next
invocation's ``message`` list.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
from typing import Annotated, Any, TypedDict

from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    InvocationsHostServer,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

load_dotenv()


def _ignore_graph_lifecycle_event(_tracer: Any, _event: Any) -> None:
    return None


def _install_otel_langgraph_callback_compatibility() -> None:
    """Prevent generic Microsoft OTel tracers from receiving unknown hooks."""
    try:
        from microsoft.opentelemetry._genai._langchain._tracer import (
            LangChainTracer as MicrosoftLangChainTracer,
        )
    except ImportError:
        return

    # The instrumentor injects this tracer after LangGraph filters generic
    # handlers from its lifecycle callback manager.
    for callback_name in ("on_interrupt", "on_resume"):
        if not hasattr(MicrosoftLangChainTracer, callback_name):
            setattr(
                MicrosoftLangChainTracer,
                callback_name,
                _ignore_graph_lifecycle_event,
            )


_AZURE_AI_SCOPE = "https://ai.azure.com/.default"
_SENSITIVE_TOOLS = {"book_trip"}
_SYSTEM_PROMPT = """You are a concise trip-planning assistant.
For a trip request, first call search_flights and search_hotels to gather options.
Then recommend a specific flight and hotel in one short paragraph and call book_trip
with that choice. The application obtains human approval before book_trip executes,
so do not ask for confirmation yourself. After booking, give a short confirmation
summary with the confirmation number.
At every step, write a brief user-visible progress message before making tool calls.
Compose that message yourself from the current context. Keep exploration,
recommendation and booking, and final confirmation visibly separated, but do not
emit a canned checklist or application-style status text.
Call simulate_crash only when the user explicitly asks you to simulate a crash.
After any tool result, continue the task and explain the result naturally.
Never claim that you used a tool unless you actually called it."""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_real_model() -> BaseChatModel:
    deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    credential = DefaultAzureCredential()
    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/"),
        credential=credential,
    )
    openai_client = project.get_openai_client()
    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        streaming=True,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value, got {value!r}")


async def _sigkill_current_process() -> None:
    print("Crash trigger received; sending SIGKILL to current process.", flush=True)
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    os.kill(os.getpid(), kill_signal)
    await asyncio.sleep(60 * 60 * 24)


@tool
def search_flights(city: str) -> dict[str, Any]:
    """Search round-trip flight options to a destination city."""
    return {
        "city": city,
        "options": [
            {"label": f"{city} Express AA123", "price_usd": 780, "stops": 0},
            {"label": f"{city} Saver BB456", "price_usd": 540, "stops": 1},
        ],
    }


@tool
def search_hotels(city: str) -> dict[str, Any]:
    """Search hotel options in a destination city."""
    return {
        "city": city,
        "options": [
            {
                "label": f"{city} Grand Hotel",
                "price_per_night_usd": 240,
                "rating": 4.6,
            },
            {
                "label": f"{city} Budget Inn",
                "price_per_night_usd": 95,
                "rating": 4.0,
            },
        ],
    }


@tool
def book_trip(
    city: str,
    nights: int = 1,
    flight: str = "",
    hotel: str = "",
) -> dict[str, Any]:
    """Book and pay for a selected flight and hotel after human approval."""
    booking_arguments = json.dumps(
        {
            "city": city,
            "flight": flight,
            "hotel": hotel,
            "nights": nights,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(booking_arguments.encode("utf-8")).hexdigest()
    confirmation = f"TRIP-{digest[:12].upper()}"
    return {
        "status": "booked",
        "confirmation": confirmation,
        "city": city,
        "nights": nights,
        "flight": flight or "(cheapest)",
        "hotel": hotel or "(recommended)",
    }


@tool
async def simulate_crash(config: RunnableConfig) -> str:
    """Crash this agent process to demonstrate durable checkpoint recovery.

    Call this tool only when the user explicitly asks to simulate a crash.
    """
    invocation_context = config.get("configurable", {}).get("invocation_context")
    if getattr(invocation_context, "entry_mode", None) == "recovered":
        return (
            "Crash recovery succeeded; resumed the pending tool call from checkpoint."
        )
    await _sigkill_current_process()
    return "The process did not terminate."


def build_graph(checkpointer, model: BaseChatModel):
    all_tools = [search_flights, search_hotels, book_trip, simulate_crash]
    tools_by_name = {selected_tool.name: selected_tool for selected_tool in all_tools}
    tool_model = model.bind_tools(all_tools)

    async def agent(state: AgentState, config: RunnableConfig) -> dict:
        response = await tool_model.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), *state["messages"]],
            config=config,
        )
        return {"messages": [response]}

    async def approval(state: AgentState, config: RunnableConfig) -> dict:
        message = state["messages"][-1]
        if not isinstance(message, AIMessage):
            raise TypeError("Approval requires an AIMessage with tool calls")

        outputs: list[ToolMessage] = []
        for tool_call in message.tool_calls:
            tool_name = tool_call["name"]
            if tool_name in _SENSITIVE_TOOLS:
                approved = interrupt(
                    {
                        "action": tool_name,
                        "arguments": tool_call["args"],
                        "tool_call_id": tool_call["id"],
                        "prompt": "Approve this sensitive tool call?",
                    }
                )
                if not approved:
                    outputs.append(
                        ToolMessage(
                            content="Tool call rejected by the user.",
                            name=tool_name,
                            tool_call_id=tool_call["id"],
                        )
                    )
                    continue
            result = await tools_by_name[tool_name].ainvoke(
                tool_call["args"],
                config=config,
            )
            outputs.append(
                ToolMessage(
                    content=json.dumps(result),
                    name=tool_name,
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}

    def route_after_agent(state: AgentState) -> str:
        message = state["messages"][-1]
        if isinstance(message, AIMessage) and message.tool_calls:
            if any(
                tool_call["name"] in _SENSITIVE_TOOLS
                for tool_call in message.tool_calls
            ):
                return "approval"
            return "tools"
        return "end"

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(all_tools))
    builder.add_node("approval", approval)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "approval": "approval", "end": END},
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("approval", "agent")
    return builder.compile(checkpointer=checkpointer)


async def amain() -> None:
    # Resilient handlers are re-invoked after a crash. Keep durable workflow
    # data in graph state and make every node's external effects idempotent.
    _install_otel_langgraph_callback_compatibility()
    options = ResponsesServerOptions(
        resilient_background=True,
        steerable_conversations=env_bool("STEERABLE_CONVERSATIONS"),
    )
    checkpointer = FoundryCheckpointSaver(user_isolation=True)
    graph = build_graph(checkpointer, build_real_model())
    server = InvocationsHostServer(graph, options=options)
    await server.run_async(port=int(os.environ.get("PORT", "8088")))


if __name__ == "__main__":
    asyncio.run(amain())
