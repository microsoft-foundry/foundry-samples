"""
System Utility Agent (cross-OS, container-aware) — NO local files required.

Tools included (per your request):
- capability_report
- system_info
- resource_snapshot
- list_processes
- process_details
- check_port
- dns_lookup
- list_environment_variables
"""

from __future__ import annotations

import datetime
import os
import json

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dataclasses import dataclass, field
from typing import Any, Dict, List, AsyncGenerator, Union
from azure.ai.agentserver.core import AgentRunContext, FoundryCBAgent
from azure.ai.agentserver.core.models import (
    Response as OpenAIResponse,
    ResponseStreamEvent,
)
from azure.ai.agentserver.core.models.projects import (
    ItemContentOutputText,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseOutputItemAddedEvent,
    ResponsesAssistantMessageItemResource,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
)
from azure.ai.agentserver.core.logger import get_logger
from dotenv import load_dotenv
from openai import AzureOpenAI
from local_tools import TOOLS, TOOL_IMPL

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

logger = get_logger()

# -----------------------------
# Agent loop (OpenAI-style tool calling)
# -----------------------------

SYSTEM_PROMPT = """You are a System Utility Agent.
You can inspect the runtime environment using tools (processes, ports, resources, DNS).
Important:
- Always call capability_report early when the user asks questions that might depend on host vs container visibility.
- Never claim you can see host-wide processes/ports unless capability_report indicates it.
- Prefer using tools over guessing.
- Keep outputs clear and actionable.
"""


@dataclass
class AgentConfig:
    model: str = field(default_factory=lambda: os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5"))
    project_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_AI_PROJECT_ENDPOINT", ""))
    max_turns: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_TURNS", "10")))
    chat_history_length: int = field(default_factory=lambda: int(os.getenv("AGENT_CHAT_HISTORY_LENGTH", "20")))
    openai_api_version: str = field(default_factory=lambda: os.getenv("OPENAI_API_VERSION", "2025-11-15-preview"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", ""))
    azure_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_ENDPOINT", ""))


class SystemUtilityAgent(FoundryCBAgent):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.cfg = AgentConfig()
        if not self.cfg.project_endpoint:
            self.client = AzureOpenAI(
                api_version=self.cfg.openai_api_version,
                azure_endpoint=self.cfg.azure_endpoint,
                api_key=self.cfg.openai_api_key,
            )
            logger.info("Using AzureOpenAI client with key-based auth.")
        else:
            self.project_client = AIProjectClient(
                endpoint=self.cfg.project_endpoint,
                credential=DefaultAzureCredential(),
            )
            self.client = self.project_client.get_openai_client()
        
        self.hit_limit_warning = f"I hit the {self.cfg.max_turns} max turn limit for this turn. Try rephrasing."

    def init_tracing_internal(self, exporter_endpoint=None, app_insights_conn_str=None):
        # optional: for local debugging, export spans to console
        trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    def _stream_final_text(self, final_text: str, context: AgentRunContext):
        """Yield streaming events for the provided final text."""

        async def _async_stream():
            assembled = ""
            sequence_number = 0

            def next_sequence_number() -> int:
                nonlocal sequence_number
                current = sequence_number
                sequence_number += 1
                return current

            yield ResponseCreatedEvent(sequence_number=next_sequence_number(), response=OpenAIResponse(output=[]))
            item_id = context.id_generator.generate_message_id()
            yield ResponseOutputItemAddedEvent(
                sequence_number=next_sequence_number(),
                output_index=0,
                item=ResponsesAssistantMessageItemResource(
                    id=item_id,
                    status="in_progress",
                    content=[ItemContentOutputText(text="", annotations=[])],
                ),
            )

            words = final_text.split(" ")
            for idx, token in enumerate(words):
                piece = token if idx == len(words) - 1 else token + " "
                assembled += piece
                yield ResponseTextDeltaEvent(
                    sequence_number=next_sequence_number(),
                    output_index=0,
                    content_index=0,
                    delta=piece,
                )

            yield ResponseTextDoneEvent(
                sequence_number=next_sequence_number(),
                output_index=0,
                content_index=0,
                text=assembled,
            )
            yield ResponseCompletedEvent(
                sequence_number=next_sequence_number(),
                response=OpenAIResponse(
                    agent=context.get_agent_id_object(),
                    conversation=context.get_conversation_object(),
                    metadata={},
                    temperature=0.0,
                    top_p=0.0,
                    user="user",
                    id=context.response_id,
                    created_at=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                    output=[
                        ResponsesAssistantMessageItemResource(
                            id=item_id,
                            status="completed",
                            content=[ItemContentOutputText(text=assembled, annotations=[])],
                        )
                    ],
                )
            )

        return _async_stream()

    def _final_text_to_response(self, final_text: str, context: AgentRunContext) -> OpenAIResponse:
        """Convert final text to a non-streaming OpenAIResponse."""
        return OpenAIResponse({
            "object": "response",
            "agent": context.get_agent_id_object(),
            "conversation": context.get_conversation_object(),
            "metadata": {},
            "type": "message",
            "role": "assistant",
            "user": "",
            "id": context.response_id,
            "created_at": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            "output_text": final_text,
            "status": "completed",
        })

    async def agent_run(  # pylint: disable=too-many-statements
        self, context: AgentRunContext
    ) -> Union[
        OpenAIResponse,
        AsyncGenerator[ResponseStreamEvent, Any],
    ]:
        span = trace.get_current_span()
        is_stream = context.request.get("stream", False)
        request_input = context.request.get("input")
        logger.info(f"Received user input: {request_input}")
        if isinstance(request_input, str):
            request_input = [{"type": "message", "role": "user", "content": request_input}]
        
        input_messages: List[Dict[str, Any]] = [
            {"type": "message", "role": "system", "content": SYSTEM_PROMPT}
        ]
        input_messages += request_input
        span.set_attribute("gen_ai.conversation.id", context.conversation_id)

        current_conv = None
        try:
            current_conv = self.client.conversations.retrieve(conversation_id=context.conversation_id)
        except Exception as e:
            logger.warning(f"Failed to retrieve conversation {context.conversation_id}: {e}. Agent will work without prior history.")
        total_input_tokens = 0
        total_output_tokens = 0
        # Tool-calling loop: keep asking the model until it returns a final answer
        for n in range(self.cfg.max_turns):  # prevent runaway loops
            with self.tracer.start_as_current_span("SystemUtilityAgent.agent_run_iteration") as iter_span:
                iter_span.set_attribute("gen_ai.request.model", self.cfg.model)
                request_payload = {
                    "model": self.cfg.model,
                    "input": input_messages[-self.cfg.chat_history_length :],
                    "tools": TOOLS,
                }
                if current_conv:
                    request_payload["conversation"] = current_conv.id
                
                resp = self.client.responses.create(**request_payload)
                
                if current_conv:
                    # reset this to avoid duplicate input items in conversation
                    input_messages = []
                else:
                    # in local mode, keep accumulating input messages for current agent run
                    input_messages += resp.output
                    
                iter_span.set_attribute("current_iteration", n)
                iter_span.set_attribute("gen_ai.input.messages", json.dumps(input_messages, default=str)[:2048])
                usage = getattr(resp, "usage", None) or (resp.get("usage") if isinstance(resp, dict) else None)
                if usage:
                    def uget(k):
                        return getattr(usage, k, None) if not isinstance(usage, dict) else usage.get(k)
                    input_tokens = uget("input_tokens") or uget("prompt_tokens") or 0
                    output_tokens = uget("output_tokens") or uget("completion_tokens") or 0
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    iter_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                    iter_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                # Find tool calls; if none, print assistant text and break
                called_any = False
                assistant_text_chunks: List[str] = []
                for item in resp.output:
                    item_type = item.type
                    if item_type == "message":
                        # Try to extract assistant text
                        txt = extract_text(item)
                        if txt:
                            assistant_text_chunks.append(txt)
                        continue
                    # Tool call items often look like: {"type":"function_call", "name":..., "arguments":...}
                    if item_type == "function_call":
                        with self.tracer.start_as_current_span("SystemUtilityAgent.tool_call_execution") as tool_span:
                            called_any = True
                            name, args, call_id = extract_tool_call(item)
                            tool_span.set_attribute("gen_ai.tool.name", name)
                            tool_span.set_attribute("gen_ai.tool.type", "function")
                            tool_span.set_attribute("gen_ai.tool.call.id", call_id or "")
                            tool_span.set_attribute(
                                "gen_ai.tool.call.arguments",
                                json.dumps(args or {}, default=str)[:1024],
                            )
                            if name not in TOOL_IMPL:
                                tool_result = {"supported": False, "reason": f"Unknown tool: {name}", "data": None}
                                tool_span.set_status(Status(StatusCode.ERROR, "Unknown tool"))
                            else:
                                try:
                                    tool_result = TOOL_IMPL[name](**(args or {}))
                                    tool_span.set_status(Status(StatusCode.OK))
                                except Exception as e:
                                    tool_span.record_exception(e)
                                    tool_span.set_status(Status(StatusCode.ERROR, str(e)))
                                    tool_result = {"supported": False, "reason": f"Tool error: {type(e).__name__}: {e}", "data": None}
                            # Append tool result back to the conversation
                            input_messages.append({
                                "type": "function_call_output",
                                "call_id": call_id or name,
                                "output": json.dumps(tool_result),
                            })
                            tool_span.set_attribute("gen_ai.tool.call.result", json.dumps(tool_result, default=str))
            if not called_any:
                # No tool calls; return final assistant text
                final_text = "\n".join(assistant_text_chunks).strip()
                span.set_attribute("gen_ai.usage.input_tokens", total_input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", total_output_tokens)
                if is_stream:
                    return self._stream_final_text(final_text, context)
                else:
                    return self._final_text_to_response(final_text, context)
                
        span.set_attribute("gen_ai.usage.input_tokens", total_input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", total_output_tokens)
        logger.warning(self.hit_limit_warning)
        if is_stream:
            return self._stream_final_text(self.hit_limit_warning, context)
        else:
            return self._final_text_to_response(self.hit_limit_warning, context)

def extract_text(item: Any) -> str:
    # Best-effort extraction across server variants
    if isinstance(item, dict):
        if item.get("type") == "output_text":
            return item.get("text", "") or ""
        if item.get("type") == "message":
            content = item.get("content", [])
            out = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "output_text":
                    out.append(c.get("text", "") or "")
            return "\n".join(out).strip()
        return ""

    # SDK objects
    t = getattr(item, "type", None)
    if t == "output_text":
        return getattr(item, "text", "") or ""
    if t == "message":
        content = getattr(item, "content", None) or []
        out = []
        for c in content:
            if getattr(c, "type", None) == "output_text":
                out.append(getattr(c, "text", "") or "")
        return "\n".join(out).strip()
    return ""


def extract_tool_call(item: Any):
    """
    Return (name, args_dict, call_id) from tool call objects/dicts.
    """
    if isinstance(item, dict):
        name = item.get("name") or (item.get("function", {}) or {}).get("name")
        arguments = item.get("arguments") or (item.get("function", {}) or {}).get("arguments")
        call_id = item.get("call_id") or item.get("id")

        args = {}
        if isinstance(arguments, dict):
            args = arguments
        elif isinstance(arguments, str) and arguments.strip():
            # local servers sometimes send JSON string
            try:
                import json
                args = json.loads(arguments)
            except Exception:
                args = {}
        return name, args, call_id

    # SDK object
    name = getattr(item, "name", None) or getattr(getattr(item, "function", None), "name", None)
    arguments = getattr(item, "arguments", None) or getattr(getattr(item, "function", None), "arguments", None)
    call_id = getattr(item, "call_id", None) or getattr(item, "id", None)

    args = {}
    if isinstance(arguments, dict):
        args = arguments
    elif isinstance(arguments, str) and arguments.strip():
        try:
            import json
            args = json.loads(arguments)
        except Exception:
            args = {}
    return name, args, call_id


if __name__ == "__main__":
    # used for local development and testing, for hosted agent deployed to Foundry, please put env vars into agent.yaml
    load_dotenv()

    system_agent = SystemUtilityAgent()
    system_agent.run()
