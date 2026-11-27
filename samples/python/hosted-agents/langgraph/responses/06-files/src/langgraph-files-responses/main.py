# Copyright (c) Microsoft. All rights reserved.

"""LangGraph agent with local file tools and a code interpreter (Responses).

Exports a LangGraph agent for the configuration-driven
`langchain_azure_ai.agents.hosting.run` entrypoint. The
agent has three local filesystem tools and the `code_interpreter` tool
loaded from a Foundry Toolbox via
`langchain_azure_ai.tools.AzureAIProjectToolbox`.

In hosted mode the platform mounts session-uploaded files into the
agent's working directory, so the same local tools work against
user-provided files. The bundled `resources/` directory ships with the
container image so the local-only demo path works without uploading
anything.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI

from langchain_azure_ai.tools import AzureAIProjectToolbox

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

_INSTRUCTIONS = (
    "You are a friendly assistant. Keep your answers brief. Make sure all "
    "mathematical calculations are performed using the code interpreter "
    "instead of mental arithmetic."
)


# ── Local file tools ─────────────────────────────────────────────────
@tool
def get_cwd() -> str:
    """Return the agent's current working directory."""
    try:
        return os.getcwd()
    except Exception as exc:
        return f"Error getting current working directory: {exc}"


@tool
def list_files(
    directory: Annotated[str, "Absolute or relative directory to list."],
) -> str:
    """List the entries in a directory."""
    try:
        return "\n".join(os.listdir(directory))
    except Exception as exc:
        return f"Error listing files in {directory}: {exc}"


@tool
def read_file(
    file_path: Annotated[str, "Path to a UTF-8 text file to read."],
) -> str:
    """Return the contents of a text file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        return f"Error reading file {file_path}: {exc}"


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


# ── Toolbox tools ────────────────────────────────────────────────────
async def _load_toolbox_tools() -> list[BaseTool]:
    toolbox = AzureAIProjectToolbox(toolbox_name=os.environ["TOOLBOX_NAME"])
    tools = await toolbox.get_tools()
    logger.info(
        "Loaded %d tool(s) from Foundry Toolbox '%s':",
        len(tools),
        toolbox.toolbox_name,
    )
    for t in tools:
        logger.info("Loaded toolbox tool: %s", t.name)
    return tools


async def create_graph():
    """Create the graph after loading the configured Foundry Toolbox."""
    toolbox_tools = await _load_toolbox_tools()
    return create_agent(
        _build_chat_model(),
        tools=[get_cwd, list_files, read_file, *toolbox_tools],
        system_prompt=_INSTRUCTIONS,
    )
