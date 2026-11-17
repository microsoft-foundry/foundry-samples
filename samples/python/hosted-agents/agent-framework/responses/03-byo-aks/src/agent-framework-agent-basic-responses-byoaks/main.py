# Copyright (c) Microsoft. All rights reserved.

import os
from urllib.parse import urlsplit

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

_CHAT_COMPLETION_ALLOWED_OPTIONS = frozenset({
    "allow_multiple_tool_calls",
    "frequency_penalty",
    "instructions",
    "logit_bias",
    "logprobs",
    "max_completion_tokens",
    "max_tokens",
    "n",
    "parallel_tool_calls",
    "presence_penalty",
    "response_format",
    "seed",
    "stop",
    "temperature",
    "tool_choice",
    "tools",
    "top_logprobs",
    "top_p",
})


def _filter_chat_completion_options(_request, options: dict):
    return {k: v for k, v in options.items() if k in _CHAT_COMPLETION_ALLOWED_OPTIONS}


def _resolve_openai_v1_base_url(project_endpoint: str) -> str:
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if openai_endpoint:
        return f"{openai_endpoint.rstrip('/')}/openai/v1/"
    parts = urlsplit(project_endpoint)
    return f"{parts.scheme}://{parts.netloc}/openai/v1/"


def _create_client(model_name: str):
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise RuntimeError(
            "Project endpoint is not configured. Set "
            "FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT."
        )

    if model_name.lower().startswith("gpt-oss-"):
        credential = AsyncDefaultAzureCredential()

        async def token_provider() -> str:
            token = await credential.get_token("https://cognitiveservices.azure.com/.default")
            return token.token

        return OpenAIChatCompletionClient(
            model=model_name,
            base_url=_resolve_openai_v1_base_url(project_endpoint),
            api_key=token_provider,
        )

    return FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model_name,
        credential=DefaultAzureCredential(),
    )


def main():
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. Set "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    is_chat_completion_model = model_name.lower().startswith("gpt-oss-")
    client = _create_client(model_name)

    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        default_options=None if is_chat_completion_model else {"store": False},
    )

    server = ResponsesHostServer(
        agent,
        prepare_options=_filter_chat_completion_options if is_chat_completion_model else None,
    )
    server.run()


if __name__ == "__main__":
    main()
