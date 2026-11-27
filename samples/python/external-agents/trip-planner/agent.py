"""Contoso trip planner: a Microsoft Agent Framework agent that runs outside Foundry.

It exports OpenTelemetry traces to the Application Insights resource connected to the
Foundry project. Foundry reads them after the agent is registered (see 01_register_agent.py).
Contoso Travel, its tools and all data are fictional.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from opentelemetry.sdk.trace import SpanProcessor

load_dotenv()

AGENT_ID = os.environ.get("OTEL_AGENT_ID", "contoso-trip-planner")


@dataclass
class AgentAnswer:
    """One agent turn: the final text, the full message list, and its trace ID."""

    text: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str | None = None


class _InvokeAgentTraceRecorder(SpanProcessor):
    """Span processor that remembers the trace ID of the latest invoke_agent span."""

    def __init__(self) -> None:
        super().__init__()
        self.last_trace_id: str | None = None

    def on_start(self, span, parent_context=None) -> None:
        """Record the trace ID when an invoke_agent span starts."""
        if span.name.startswith("invoke_agent"):
            self.last_trace_id = format(span.get_span_context().trace_id, "032x")

    def on_end(self, span) -> None:
        """No-op."""

    def shutdown(self) -> None:
        """No-op."""

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """No-op."""
        return True


_TRACE_RECORDER = _InvokeAgentTraceRecorder()


def configure_telemetry() -> None:
    """Send agent traces, including message content, to Application Insights."""
    from microsoft.opentelemetry import use_microsoft_opentelemetry
    from opentelemetry import trace

    use_microsoft_opentelemetry(
        enable_azure_monitor=True,
        azure_monitor_connection_string=os.environ[
            "APPLICATIONINSIGHTS_CONNECTION_STRING"
        ],
        sampling_ratio=1.0,
        enable_sensitive_data=True,
    )
    trace.get_tracer_provider().add_span_processor(_TRACE_RECORDER)


def flush_telemetry() -> None:
    """Export buffered spans before the process exits."""
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=30_000)


def build_agent(instructions_version: str, skills_dir: str | Path | None = None):
    """Create the trip-planner agent with the chosen instructions and optional skills folder."""
    from agent_framework import Agent, SkillsProvider
    from agent_framework.openai import OpenAIChatCompletionClient
    from azure.identity import AzureCliCredential

    from instructions import INSTRUCTIONS
    from travel_tools import TOOLS

    client = OpenAIChatCompletionClient(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        # Not DefaultAzureCredential: its managed-identity probe fails off-Azure and is traced as a failed
        # call. When you deploy, use the credential for your host, such as WorkloadIdentityCredential on AKS.
        credential=AzureCliCredential(),
    )
    context_providers = []
    if skills_dir:
        # Review downloaded skills before using them. Loading doesn't need approval here;
        # running a skill's scripts still does by default.
        context_providers.append(
            SkillsProvider.from_paths(skills_dir, disable_load_skill_approval=True)
        )
    return Agent(
        client,
        INSTRUCTIONS[instructions_version],
        id=AGENT_ID,  # Emitted as gen_ai.agent.id. 01_register_agent.py uses the same ID.
        name=AGENT_ID,
        description="Contoso Travel trip planner (fictional).",
        tools=TOOLS,
        context_providers=context_providers or None,
    )


def to_evaluator_messages(messages) -> list[dict[str, Any]]:
    """Convert Agent Framework messages to the message format Foundry evaluators read."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        for content in message.contents:
            if content.type == "function_call":
                arguments = content.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments or "{}")
                converted.append(
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_call",
                                "tool_call_id": content.call_id,
                                "name": content.name,
                                "arguments": arguments,
                            }
                        ],
                    }
                )
            elif content.type == "function_result":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": content.call_id,
                        "content": [
                            {"type": "tool_result", "tool_result": content.result}
                        ],
                    }
                )
            elif content.type == "text" and content.text:
                converted.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": content.text}],
                    }
                )
    return converted


async def ask(agent, question: str) -> AgentAnswer:
    """Run one single-turn request and return the answer with its messages and trace ID."""
    _TRACE_RECORDER.last_trace_id = None
    response = await agent.run(question)
    return AgentAnswer(
        text=response.text,
        messages=to_evaluator_messages(response.messages),
        trace_id=_TRACE_RECORDER.last_trace_id,
    )


def main() -> None:
    """Ask the agent one question from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--instructions", choices=["v1", "v2"], default="v1")
    parser.add_argument(
        "--skills", help="Folder with SKILL.md skills to load, such as ./skills."
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    configure_telemetry()
    agent = build_agent(args.instructions, args.skills)
    try:
        answer = asyncio.run(ask(agent, args.question))
        print(answer.text)
        print(f"\n(trace ID: {answer.trace_id})")
    finally:
        flush_telemetry()


if __name__ == "__main__":
    main()
