# Copyright (c) Microsoft. All rights reserved.

"""LangGraph multi-agent workflow (Responses protocol).

Exports a custom LangGraph ``StateGraph`` for the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint. The
graph chains three specialized LLM nodes — a slogan writer, a legal
reviewer, and a formatter — that each see only the previous agent's
output (equivalent to Agent Framework's ``context_mode="last_agent"``).

Only the formatter's message is appended to the Responses output;
the writer and legal-reviewer drafts live on a private ``draft``
channel of the graph state.
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
from typing_extensions import TypedDict

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

_WRITER_PROMPT = (
    "You are an excellent slogan writer. You create new slogans based on "
    "the given topic."
)
_LEGAL_PROMPT = (
    "You are an excellent legal reviewer. Make necessary corrections to "
    "the slogan so that it is legally compliant."
)
_FORMAT_PROMPT = (
    "You are an excellent content formatter. You take the slogan and "
    "format it in a cool retro style when printing to a terminal."
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
        # LangGraph manages message history instead of the model service.
        store=False,
    )


# ── Graph ────────────────────────────────────────────────────────────
class State(TypedDict):
    """Graph state.

    ``messages`` is the channel the Responses host reads — only the
    formatter writes to it, so only its output is returned. ``draft``
    is a private scratchpad passed between writer → legal → formatter,
    mirroring Agent Framework's ``context_mode="last_agent"``.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    draft: str


def _build_graph(model: ChatOpenAI):
    async def writer(state: State) -> dict:
        topic = state["messages"][-1].content
        result = await model.ainvoke(
            [SystemMessage(content=_WRITER_PROMPT), HumanMessage(content=topic)]
        )
        return {"draft": result.content}

    async def legal_reviewer(state: State) -> dict:
        result = await model.ainvoke(
            [SystemMessage(content=_LEGAL_PROMPT), HumanMessage(content=state["draft"])]
        )
        return {"draft": result.content}

    async def formatter(state: State) -> dict:
        result = await model.ainvoke(
            [SystemMessage(content=_FORMAT_PROMPT), HumanMessage(content=state["draft"])]
        )
        return {"messages": [AIMessage(content=result.content)]}

    builder = StateGraph(State)
    builder.add_node("writer", writer)
    builder.add_node("legal_reviewer", legal_reviewer)
    builder.add_node("formatter", formatter)
    builder.add_edge(START, "writer")
    builder.add_edge("writer", "legal_reviewer")
    builder.add_edge("legal_reviewer", "formatter")
    builder.add_edge("formatter", END)
    return builder.compile()


def create_graph():
    """Create the workflow graph loaded by the hosting entrypoint."""
    return _build_graph(_build_chat_model())
