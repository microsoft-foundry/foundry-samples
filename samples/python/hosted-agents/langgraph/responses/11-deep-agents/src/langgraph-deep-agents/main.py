# Copyright (c) Microsoft. All rights reserved.

"""Host the deep research agent on Microsoft Foundry over Responses."""

from __future__ import annotations

import asyncio
import logging
import os

from agent import build_agent
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from report_export import create_report_export_tool
from research_agent.tools import load_tools
from utils import build_chat_model

load_dotenv()

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "false")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    async with FoundryCheckpointSaver() as checkpointer:
        tools = await load_tools()
        with DefaultAzureCredential() as credential:
            report_export_tool = create_report_export_tool(credential)
            agent = build_agent(
                build_chat_model(), checkpointer, tools, report_export_tool
            )
            port = int(os.environ.get("PORT", "8088"))
            host = ResponsesHostServer(agent)
            logger.info(
                "Starting Deep Agents host with Entra-authenticated report downloads"
            )
            await host.run_async(port=port)


if __name__ == "__main__":
    asyncio.run(main())
