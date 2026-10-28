# Copyright (c) Microsoft. All rights reserved.

"""LangGraph human-in-the-loop agent (Responses protocol).

Exports a LangGraph ``StateGraph`` for the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint. The
graph drafts a proposal in response to the user's task and pauses for
human review via ``langgraph.types.interrupt``. Each pause is
serialized to the wire as the standard OpenAI ``mcp_approval_request``
output item plus a paired ``function_call`` channel for richer resume
payloads.

Three review decisions are supported:

* **Approve** — client sends ``mcp_approval_response`` with
  ``approve: true``; the host resumes the graph and the final draft is
  emitted as the assistant message.
* **Reject** — client sends ``mcp_approval_response`` with
  ``approve: false``; the host returns ``response.failed`` with
  ``code="interrupt_rejected"``. The checkpoint is preserved so the
  client can retry.
* **Revise** — client sends ``function_call_output`` with
  ``output='{"resume": {"feedback": "<text>"}}'``; the graph loops
  back to the ``draft`` node with the feedback appended to the
  revision history.

State is persisted by ``FoundryCheckpointSaver`` and keyed by the
``conversation`` id, so paused runs survive process restarts.
"""

from __future__ import annotations

import os
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

_DRAFT_PROMPT = (
    "You are a professional assistant. The user will give you a task. "
    "Generate a high-quality draft proposal that the user can review and "
    "approve. Be detailed, well-structured, and ready for review. If "
    "revision feedback is provided, incorporate it into an improved "
    "version of the proposal."
)


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
    )


# ── Graph ────────────────────────────────────────────────────────────
class State(TypedDict):
    """Graph state.

    ``messages`` is the channel the Responses host reads — only the
    final approved draft is appended to it. ``draft`` holds the current
    proposal text, and ``revision_history`` accumulates prior drafts
    with the feedback that prompted each revision.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    draft: str
    revision_history: list[dict]


def _build_graph(model: ChatOpenAI):
    async def draft(state: State) -> dict:
        task = state["messages"][0].content
        msgs: list[BaseMessage] = [
            SystemMessage(content=_DRAFT_PROMPT),
            HumanMessage(content=f"Task: {task}"),
        ]
        for rev in state.get("revision_history", []):
            msgs.append(AIMessage(content=rev["draft"]))
            msgs.append(HumanMessage(content=f"Revision feedback: {rev['feedback']}"))
        result = await model.ainvoke(msgs)
        return {"draft": result.content}

    def await_approval(state: State) -> Command:
        # Pause until the client returns a decision. On approve=True the
        # resume value is the original ``proposed`` dict (echoed back).
        # On a rich ``function_call_output`` resume the client can send
        # ``{"feedback": "<text>"}`` to request a revision. Reject never
        # re-enters this node — the host short-circuits to
        # response.failed code="interrupt_rejected".
        resume = interrupt({"draft": state["draft"]})

        if isinstance(resume, dict) and resume.get("feedback"):
            new_history = state.get("revision_history", []) + [
                {"draft": state["draft"], "feedback": resume["feedback"]}
            ]
            return Command(update={"revision_history": new_history}, goto="draft")

        return Command(
            update={"messages": [AIMessage(content=state["draft"])]},
            goto=END,
        )

    builder = StateGraph(State)
    builder.add_node("draft", draft)
    builder.add_node("await_approval", await_approval)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "await_approval")
    checkpointer = FoundryCheckpointSaver(user_isolation=True)
    return builder.compile(checkpointer=checkpointer)


def create_graph():
    """Create the human-in-the-loop graph loaded by the hosting entrypoint."""
    return _build_graph(_build_chat_model())
