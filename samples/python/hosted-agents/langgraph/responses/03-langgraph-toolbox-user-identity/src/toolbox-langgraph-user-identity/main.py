# Copyright (c) Microsoft. All rights reserved.

"""LangGraph toolbox agent with user-identity MCP tools (Responses protocol).

Exports a LangGraph agent built with `langchain.agents.create_agent` for the
configuration-driven `langchain_azure_ai.agents.hosting.run` entrypoint.
Tools are loaded at startup from a Foundry Toolbox via
`langchain_azure_ai.tools.AzureAIProjectToolbox`.

The toolbox contains WorkIQ Mail, WorkIQ Calendar, and GitHub MCP
connections that authenticate on behalf of the calling user. When a
connection returns an OAuth consent error (MCP code ``-32006``), the sample
surfaces the consent URL through a tool message instead of crashing the turn.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are a helpful assistant with access to tools through
Foundry Toolbox, including the calling user's mail, calendar, and GitHub tools
when configured.

Use a matching tool whenever the request depends on the user's data. When a code
interpreter is available, use it to perform calculations and base your answer on
its result rather than doing arithmetic yourself or estimating the answer.
Summarize only the information needed to answer the request. When a tool returns
source URLs, include a brief "Sources" section listing the titles and URLs you
used. Do not invent citations. If OAuth consent is required, return the complete
consent URL verbatim so the user can authorize the connection.
"""


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


# ── OAuth consent handling ───────────────────────────────────────────
_CONSENT_ERROR_CODE = -32006
_CONSENT_HOSTS = ("consent.azure-apim.net", "consent.azure-apihub.net")


def _is_consent_host(host: str | None) -> bool:
    return bool(
        host
        and any(
            host == consent_host or host.endswith(f".{consent_host}")
            for consent_host in _CONSENT_HOSTS
        )
    )


def _contains_consent_host(text: str) -> bool:
    for token in re.findall(r"https?://[^\s'\"<>]+", text):
        host = urlparse(token).hostname
        if _is_consent_host(host):
            return True
    return False


def _extract_consent_url(text: str) -> str | None:
    for candidate in re.findall(r"https?://[^\s)>\]\"']+", text):
        if _is_consent_host(urlparse(candidate).hostname):
            return candidate
    return None


def _is_consent_error(exc: BaseException) -> bool:
    error_data = getattr(exc, "error", None)
    if (
        error_data is not None
        and getattr(error_data, "code", None) == _CONSENT_ERROR_CODE
    ):
        return True
    if _contains_consent_host(str(exc)):
        return True
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        return any(_is_consent_error(sub) for sub in sub_exceptions)
    return False


def _consent_url_from_exception(exc: BaseException) -> str:
    error_data = getattr(exc, "error", None)
    if (
        error_data is not None
        and getattr(error_data, "code", None) == _CONSENT_ERROR_CODE
    ):
        message = getattr(error_data, "message", str(exc))
        return _extract_consent_url(message) or message
    url = _extract_consent_url(str(exc))
    if url:
        return url
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        for sub in sub_exceptions:
            nested = _consent_url_from_exception(sub)
            if nested:
                return nested
    return str(exc)


def _consent_aware_error_handler(error: Exception) -> str:
    if _is_consent_error(error):
        url = _consent_url_from_exception(error)
        return (
            "OAuth consent required. Open this URL in a browser to authorize the "
            f"toolbox connection, then retry the request: {url}"
        )
    return f"Tool error: {error}"


# ── Tool-schema sanitization ─────────────────────────────────────────
def _sanitize_tool_schema(tool: BaseTool) -> None:
    schema: Any = tool.args_schema if isinstance(tool.args_schema, dict) else None
    if schema is None:
        return
    if schema.get("type") == "object" and "properties" not in schema:
        schema["properties"] = {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    if required and not props:
        for field_name in required:
            props[field_name] = {"type": "string"}
        schema["properties"] = props


# ── Toolbox tools ────────────────────────────────────────────────────
async def _load_toolbox_tools() -> list[BaseTool]:
    toolbox = AzureAIProjectToolbox(toolbox_name=os.environ["TOOLBOX_NAME"])
    tools = await toolbox.get_tools()
    logger.info(
        "Loaded %d tool(s) from Foundry Toolbox '%s':",
        len(tools),
        toolbox.toolbox_name,
    )
    for tool in tools:
        _sanitize_tool_schema(tool)
        tool.handle_tool_error = _consent_aware_error_handler
        logger.info("Loaded toolbox tool: %s", tool.name)
    return tools


# ── Graph factory ────────────────────────────────────────────────────
async def create_graph():
    """Load Toolbox tools and create the graph used by the hosting entrypoint."""
    tools = await _load_toolbox_tools()
    return create_agent(_build_chat_model(), tools=tools, system_prompt=SYSTEM_PROMPT)
