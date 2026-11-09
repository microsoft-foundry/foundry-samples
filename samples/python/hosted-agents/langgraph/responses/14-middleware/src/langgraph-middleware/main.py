"""Run the native middleware agent with explicit startup resource ownership."""

from __future__ import annotations

import asyncio
import logging
import os

from agent import build_agent
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
)
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph


def _create_host(graph: CompiledStateGraph) -> ResponsesHostServer:
    """Use the stock host as the sole LangChain instrumentation owner."""
    os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "false")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    return ResponsesHostServer(graph)


async def main() -> None:
    """Keep credentials, model transports, and checkpoints alive until host exit."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    with DefaultAzureCredential() as credential:
        with (
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
            ) as project,
            project.get_openai_client() as endpoint_client,
        ):
            base_url = str(endpoint_client.base_url)
        model = ChatOpenAI(
            model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"),
            base_url=base_url,
            api_key=get_bearer_token_provider(
                credential, "https://ai.azure.com/.default"
            ),
            use_responses_api=True,
            output_version="responses/v1",
        )
        with model.root_client:
            async with (
                model.root_async_client,
                FoundryCheckpointSaver() as checkpointer,
            ):
                graph = build_agent(model, checkpointer)
                await _create_host(graph).run_async(
                    port=int(os.environ.get("PORT", "8088"))
                )


if __name__ == "__main__":
    asyncio.run(main())
