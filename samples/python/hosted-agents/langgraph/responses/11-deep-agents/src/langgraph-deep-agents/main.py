"""Host Deep Research with explicit model, credential, and checkpoint lifetimes."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from agent import build_agent
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from report_export import create_report_export_tool
from research_agent.tools import load_tools


async def main() -> None:
    """Keep application resources alive until the Responses host shuts down."""
    load_dotenv(Path(__file__).with_name(".env"))
    logging.basicConfig(level=logging.INFO)
    os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "false")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    with DefaultAzureCredential() as credential:
        if os.environ.get("OTEL_SDK_DISABLED", "").lower() != "true":
            enable_auto_tracing(
                credential=credential, auto_configure_azure_monitor=True
            )
        model = AzureAIOpenAIApiChatModel(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"),
            output_version="responses/v1",
        )
        with model.root_client:
            async with model.root_async_client:
                tools = await load_tools(credential)
                async with FoundryCheckpointSaver() as checkpointer:
                    graph = build_agent(
                        model,
                        checkpointer,
                        tools,
                        create_report_export_tool(credential),
                    )
                    await ResponsesHostServer(graph).run_async()


if __name__ == "__main__":
    asyncio.run(main())
