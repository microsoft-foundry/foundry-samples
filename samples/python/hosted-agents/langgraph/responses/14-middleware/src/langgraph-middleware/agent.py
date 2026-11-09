"""A standard LangChain agent with built-in and user-defined middleware."""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentState,
    HumanInTheLoopMiddleware,
    before_model,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


@before_model(can_jump_to=["end"])
def check_message_limit(
    state: AgentState, runtime: Runtime[None]
) -> dict[str, Any] | None:
    """End the turn before calling the model at 50 accumulated messages."""
    if len(state["messages"]) >= 50:
        return {
            "messages": [AIMessage(content="Conversation limit reached.")],
            "jump_to": "end",
        }
    return None


@tool
def send_email(recipient: str, subject: str, body: str) -> str:
    """Simulate sending an email; no email service is called.

    Args:
        recipient: Address of the intended recipient.
        subject: Email subject.
        body: Email body.

    Returns:
        A receipt containing the arguments that actually reached the tool.
    """
    logger.info("Simulated send_email tool executed")
    return f"Simulated email to {recipient}: {subject}\n{body}"


def build_agent(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Compose ordinary LangChain middleware, independent of any host.

    Args:
        model: A LangChain chat model supporting tool calls.
        checkpointer: The application's LangGraph checkpoint store.

    Returns:
        A compiled agent supporting native invoke, ainvoke, and streaming.
    """
    return create_agent(
        model=model,
        tools=[send_email],
        system_prompt=(
            "You are an email assistant demonstrating human review. "
            "Use send_email when asked to send an email; the tool is a simulation. "
            "After a tool rejection, explain it and do not retry unless the user "
            "explicitly asks again. Report the actual recipient from the tool result."
        ),
        middleware=[
            check_message_limit,
            HumanInTheLoopMiddleware[AgentState, None](
                interrupt_on={
                    "send_email": {"allowed_decisions": ["approve", "edit", "reject"]}
                },
                description_prefix="Review the proposed email",
            ),
        ],
        checkpointer=checkpointer,
    )
