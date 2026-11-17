# Copyright (c) Microsoft. All rights reserved.

"""LangGraph Handoff — Hosted agent with Responses protocol.

Multi-agent customer support handoff demo using LangGraph, served through
the Responses protocol for voice-first scenarios.

This sample demonstrates:
  - Multi-agent orchestration with handoff (triage → refund → order agents)
  - Using the Responses protocol with ``ResponseEventStream``
  - Streaming status updates as agents hand off and tools execute
  - Voice-optimized responses (short, conversational)
  - Structural robustness: handoff reasons, session context injection, bounce-back guards

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (auto-injected in hosted containers)
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name in the Foundry project

Usage::

    # Set environment variables
    export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
    export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1"

    # Start the agent
    python main.py

    # Invoke the agent (streaming)
    curl -sS -N -X POST http://localhost:8088/responses \\
        -H "Content-Type: application/json" \\
        -d '{"input": "I need a refund for order 12345", "stream": true}'
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from collections.abc import AsyncIterable
from typing import Any

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03dZ [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.warning(
        "APPLICATIONINSIGHTS_CONNECTION_STRING not set — traces will not be sent to "
        "Application Insights. Set it to enable local telemetry."
    )

_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
if not _endpoint:
    raise EnvironmentError(
        "FOUNDRY_PROJECT_ENDPOINT environment variable is not set. "
        "Set it to your Foundry project endpoint, or use 'azd ai agent run' "
        "which sets it automatically."
    )

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(_credential, "https://ai.azure.com/.default")

llm = ChatOpenAI(
    base_url=_endpoint.rstrip("/") + "/openai/v1",
    api_key=_token_provider,
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    use_responses_api=True,
    streaming=True,
    # The application manages message history instead of the model service.
    store=False,
)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@langchain_tool
def lookup_order_details(order_id: str) -> dict[str, str]:
    """Return synthetic order details for a given order ID."""
    normalized = "".join(ch for ch in order_id if ch.isdigit()) or order_id
    rng = random.Random(normalized)
    catalog = [
        "Wireless Headphones",
        "Mechanical Keyboard",
        "Gaming Mouse",
        "27-inch Monitor",
        "USB-C Dock",
        "Bluetooth Speaker",
        "Laptop Stand",
    ]
    return {
        "order_id": normalized,
        "item_name": catalog[rng.randrange(len(catalog))],
        "amount": f"${rng.randint(39, 349)}.{rng.randint(0, 99):02d}",
        "currency": "USD",
        "purchase_date": f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "status": "delivered",
    }


@langchain_tool
def submit_refund(refund_description: str, amount: str, order_id: str) -> str:
    """Process a refund request."""
    return f"Refund recorded for order {order_id} (amount: {amount}): {refund_description}"


@langchain_tool
def submit_replacement(order_id: str, shipping_preference: str, replacement_note: str) -> str:
    """Process a replacement request."""
    return f"Replacement recorded for order {order_id} (shipping: {shipping_preference}): {replacement_note}"


# ---------------------------------------------------------------------------
# Agent definitions (system prompts + tools + handoff targets)
# ---------------------------------------------------------------------------

AGENTS: dict[str, dict[str, Any]] = {
    "triage_agent": {
        "system": (
            "You are the customer support triage agent.\n"
            "Routing policy:\n"
            "1. Route refund-related requests to refund_agent.\n"
            "2. Route replacement/shipping requests to order_agent.\n"
            "3. If user wants both refund and replacement, route to refund_agent first.\n"
            "4. Do not force replacement if the user asked for refund only.\n"
            "5. When the issue is fully resolved, send a warm farewell and end with exactly: Case complete.\n"
            "\n"
            "RULES:\n"
            "- You MUST use a handoff tool to transfer. NEVER just describe a transfer in text.\n"
            "- If the user asks for something outside your scope, politely explain you can only help\n"
            "  with refunds and replacements, then ask if there's anything else.\n"
            "  If not, say farewell and end with: Case complete."
        ),
        "tools": [],
        "handoffs": ["refund_agent", "order_agent"],
    },
    "refund_agent": {
        "system": (
            "You are the refund specialist.\n"
            "Workflow:\n"
            "1. If order_id is missing, ask only for order_id.\n"
            "2. Once order_id is available, call lookup_order_details(order_id).\n"
            "3. Do not ask the customer how much they paid.\n"
            "4. If user intent is ambiguous, ask: refund only, replacement only, or both.\n"
            "5. Call submit_refund with order_id, amount, and description.\n"
            "6. After successful refund:\n"
            "   - If user also wants replacement: hand off to order_agent with reason explaining the refund is done.\n"
            "   - If refund only: confirm the refund briefly and say farewell. End with: Case complete.\n"
            "7. If replacement only (no refund needed): hand off to order_agent.\n"
            "\n"
            "RULES:\n"
            "- Use handoff tools to transfer. Include a clear reason.\n"
            "- After refund-only success, do NOT hand off. Say farewell yourself.\n"
            "- If unrelated to refunds, hand off to triage_agent."
        ),
        "tools": [lookup_order_details, submit_refund],
        "handoffs": ["order_agent", "triage_agent"],
    },
    "order_agent": {
        "system": (
            "You are the order specialist. Handle replacement/exchange/shipping.\n"
            "Workflow:\n"
            "1. If shipping preference is missing, ask: standard or expedited.\n"
            "2. If order_id is missing and not in context, ask for it.\n"
            "3. Call submit_replacement(order_id, shipping_preference, replacement_note).\n"
            "4. After success, confirm briefly and say farewell. End with: Case complete.\n"
            "\n"
            "RULES:\n"
            "- Use handoff tools to transfer. Include a clear reason.\n"
            "- After submit_replacement succeeds, do NOT hand off. Say farewell yourself.\n"
            "- Only hand off to refund_agent if user explicitly asks for a refund instead.\n"
            "- If unrelated to replacements, hand off to triage_agent."
        ),
        "tools": [lookup_order_details, submit_replacement],
        "handoffs": ["triage_agent", "refund_agent"],
    },
}


def _build_handoff_tool_schemas(agent_name: str) -> list[dict]:
    """Build handoff tool schemas (OpenAI format) for an agent."""
    return [
        {
            "type": "function",
            "function": {
                "name": f"handoff_to_{target}",
                "description": f"Transfer the conversation to {target}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why you are handing off. Include what has been completed and what the next agent should do.",
                        }
                    },
                    "required": ["reason"],
                },
            },
        }
        for target in AGENTS[agent_name]["handoffs"]
    ]


# ---------------------------------------------------------------------------
# Simple turn-based orchestrator (per-session state)
# ---------------------------------------------------------------------------

_session_state: dict[str, Any] = {
    "messages": [],
    "active_agent": "triage_agent",
    "completed_actions": [],  # e.g. ["refund_submitted", "replacement_submitted"]
}


def _build_context_block() -> str:
    """Build a dynamic context block injected into system prompts."""
    parts = []
    if _session_state["completed_actions"]:
        parts.append("Already completed: " + ", ".join(_session_state["completed_actions"]))
    return ("[Session context]\n" + "\n".join(parts) + "\n\n") if parts else ""


async def run_agent_turn(user_text: str) -> AsyncIterable[dict[str, Any]]:
    """Run one turn, yielding status/content events as they happen.

    Yields dicts with:
      - {"type": "status", "text": "..."} for status updates
      - {"type": "content", "text": "..."} for final response text (ainvoke mode)
      - {"type": "content_delta", "text": "..."} for streamed token chunks (astream mode)
      - {"type": "content_done"} signals end of streamed content (astream mode)
      - {"type": "agent", "name": "..."} when agent changes

    Set USE_STREAMING=true env var to enable real token streaming.
    """
    _session_state["messages"].append(HumanMessage(content=user_text))

    active_agent = _session_state["active_agent"]
    working_messages = list(_session_state["messages"])
    max_iterations = 15
    # Track handoff chain within this turn only (reset each turn)
    turn_handoff_source: str | None = None
    use_streaming = os.environ.get("USE_STREAMING", "true").lower() in ("true", "1", "yes")

    for _ in range(max_iterations):
        agent_def = AGENTS[active_agent]
        context_block = _build_context_block()
        system_msg = {"role": "system", "content": (
            "[Voice mode] Respond in short, natural sentences as if speaking aloud. "
            "No bullet points, numbered lists, markdown, code blocks, or special formatting. "
            "Keep it conversational and concise — a few sentences at most, no more than one question. "
            "Always respond in the same language the user is speaking.\n\n"
            + context_block + agent_def["system"]
        )}

        real_tools = agent_def["tools"]
        handoff_schemas = _build_handoff_tool_schemas(active_agent)
        all_tools = real_tools + [s["function"] for s in handoff_schemas]
        llm_with_tools = llm.bind_tools(all_tools)

        if use_streaming:
            # ------- astream path: real token-by-token streaming -------
            collected_content = ""
            collected_tool_calls: dict[Any, dict] = {}  # index -> {name, args_str, id}
            content_started = False

            async for chunk in llm_with_tools.astream([system_msg] + working_messages):
                # Accumulate text content
                if chunk.content:
                    delta = chunk.content if isinstance(chunk.content, str) else ""
                    if isinstance(chunk.content, list):
                        delta = "".join(
                            block.get("text", "") if isinstance(block, dict) else str(block)
                            for block in chunk.content
                        )
                    if delta:
                        if not content_started:
                            content_started = True
                        collected_content += delta
                        yield {"type": "content_delta", "text": delta}

                # Accumulate tool calls from chunks
                if chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        idx = tc_chunk.get("index", tc_chunk.get("id", len(collected_tool_calls)))
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {"name": "", "args_str": "", "id": ""}
                        if tc_chunk.get("name"):
                            collected_tool_calls[idx]["name"] = tc_chunk["name"]
                        if tc_chunk.get("args"):
                            collected_tool_calls[idx]["args_str"] += tc_chunk["args"]
                        if tc_chunk.get("id"):
                            collected_tool_calls[idx]["id"] = tc_chunk["id"]

            # Build final tool_calls list
            final_tool_calls = []
            for tc_data in collected_tool_calls.values():
                if tc_data["name"]:
                    try:
                        args = json.loads(tc_data["args_str"]) if tc_data["args_str"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    final_tool_calls.append({
                        "name": tc_data["name"],
                        "args": args,
                        "id": tc_data["id"],
                    })

            if not final_tool_calls:
                # Pure text response — done
                if content_started:
                    yield {"type": "content_done"}
                _session_state["active_agent"] = active_agent
                _session_state["messages"].append(AIMessage(content=collected_content))
                return

            # Had tool calls — build an AIMessage to append
            response = AIMessage(
                content=collected_content,
                tool_calls=final_tool_calls,
            )
        else:
            # ------- ainvoke path: wait for complete response -------
            response = await llm_with_tools.ainvoke([system_msg] + working_messages)

            if not response.tool_calls:
                raw_content = response.content or ""
                if isinstance(raw_content, list):
                    text = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in raw_content
                    )
                else:
                    text = raw_content
                _session_state["active_agent"] = active_agent
                _session_state["messages"].append(AIMessage(content=text))
                yield {"type": "content", "text": text}
                return

        # --- Common tool-call handling for both paths ---
        working_messages.append(response)

        for tc in response.tool_calls:
            tool_name = tc["name"]

            if tool_name.startswith("handoff_to_"):
                target = tool_name.replace("handoff_to_", "")
                reason = tc["args"].get("reason", "")

                # Guard: block immediate bounce-back within this turn only
                if target == turn_handoff_source and target != "triage_agent":
                    working_messages.append(
                        ToolMessage(
                            content=f"Cannot transfer back to {target} (already handed off from there this turn). "
                                    f"Handle the request yourself or transfer to a different agent.",
                            tool_call_id=tc["id"],
                        )
                    )
                elif target in AGENTS:
                    handoff_msg = f"Transferred to {target}."
                    if reason:
                        handoff_msg += f" Reason: {reason}"
                    working_messages.append(
                        ToolMessage(content=handoff_msg, tool_call_id=tc["id"])
                    )
                    # Inject a nudge so the new agent always produces a greeting
                    working_messages.append(
                        HumanMessage(content="[connected]")
                    )
                    turn_handoff_source = active_agent
                    active_agent = target
                    _session_state["active_agent"] = active_agent
                    yield {"type": "status", "text": f"Transferring to {target.replace('_', ' ')}..."}
                    yield {"type": "agent", "name": active_agent}
                    await asyncio.sleep(0.5)  # Brief pause before new agent speaks
                else:
                    working_messages.append(
                        ToolMessage(content=f"Unknown agent: {target}", tool_call_id=tc["id"])
                    )
            else:
                yield {"type": "status", "text": f"Running {tool_name.replace('_', ' ')}..."}
                tool_fn = next((t for t in real_tools if t.name == tool_name), None)
                if tool_fn:
                    try:
                        result = await tool_fn.ainvoke(tc["args"])
                        result_str = json.dumps(result) if not isinstance(result, str) else result
                    except Exception as e:
                        result_str = f"Error: {e}"
                    # Track completed actions
                    if tool_name == "submit_refund":
                        _session_state["completed_actions"].append("refund_submitted")
                    elif tool_name == "submit_replacement":
                        _session_state["completed_actions"].append("replacement_submitted")
                else:
                    result_str = f"Unknown tool: {tool_name}"
                working_messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    # Safety fallback
    _session_state["active_agent"] = active_agent
    fallback = "I'm having trouble processing your request. Please try again."
    _session_state["messages"].append(AIMessage(content=fallback))
    yield {"type": "content", "text": fallback}


# ---------------------------------------------------------------------------
# Responses protocol handler
# ---------------------------------------------------------------------------

app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
) -> AsyncIterable[dict[str, Any]]:
    """Stream LangGraph handoff output via the Responses protocol."""

    user_input = await context.get_input_text() or "Hello!"

    logger.info(
        "Processing request %s (input length=%d): %.100s",
        context.response_id, len(user_input), user_input,
    )

    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )

    yield stream.emit_created()
    yield stream.emit_in_progress()

    try:
        # Track streaming content item (for astream mode)
        streaming_content_item = None
        streaming_tc = None

        async for event in run_agent_turn(user_input):
            if cancellation_signal.is_set():
                yield stream.emit_incomplete(reason="cancelled")
                return

            if event["type"] == "status":
                # Close any in-flight streaming content before emitting status
                if streaming_tc:
                    yield streaming_tc.emit_text_done()
                    yield streaming_tc.emit_done()
                if streaming_content_item:
                    yield streaming_content_item.emit_done()
                streaming_content_item = None
                streaming_tc = None

                # Emit status as a separate output item
                s_item = stream.add_output_item_message()
                yield s_item.emit_added()
                s_tc = s_item.add_text_content()
                yield s_tc.emit_added()
                yield s_tc.emit_delta(event["text"] + "\n")
                yield s_tc.emit_text_done()
                yield s_tc.emit_done()
                yield s_item.emit_done()

            elif event["type"] == "content":
                # ainvoke mode: full content available at once
                content_item = stream.add_output_item_message()
                yield content_item.emit_added()
                tc = content_item.add_text_content()
                yield tc.emit_added()

                # Stream in chunks for natural feel
                text = event["text"]
                chunk_size = 20
                for i in range(0, len(text), chunk_size):
                    yield tc.emit_delta(text[i:i + chunk_size])

                yield tc.emit_text_done()
                yield tc.emit_done()
                yield content_item.emit_done()

            elif event["type"] == "content_delta":
                # astream mode: real token-by-token streaming
                if streaming_content_item is None:
                    streaming_content_item = stream.add_output_item_message()
                    yield streaming_content_item.emit_added()
                    streaming_tc = streaming_content_item.add_text_content()
                    yield streaming_tc.emit_added()
                yield streaming_tc.emit_delta(event["text"])

            elif event["type"] == "content_done":
                # astream mode: finalize the streaming content item
                if streaming_tc:
                    yield streaming_tc.emit_text_done()
                    yield streaming_tc.emit_done()
                if streaming_content_item:
                    yield streaming_content_item.emit_done()
                streaming_content_item = None
                streaming_tc = None

            # "agent" type events are just for internal tracking

    except Exception as exc:
        logger.exception("Agent turn failed")
        err_item = stream.add_output_item_message()
        yield err_item.emit_added()
        err_tc = err_item.add_text_content()
        yield err_tc.emit_added()
        yield err_tc.emit_delta(f"Sorry, something went wrong: {exc}")
        yield err_tc.emit_text_done()
        yield err_tc.emit_done()
        yield err_item.emit_done()

    yield stream.emit_completed()

    logger.info("Request %s completed", context.response_id)


if __name__ == "__main__":
    logger.info("Starting LangGraph Handoff Responses agent")
    app.run()
