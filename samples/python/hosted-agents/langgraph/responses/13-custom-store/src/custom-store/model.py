# Copyright (c) Microsoft. All rights reserved.

"""Foundry model configuration for hosted and on-premises deployments."""

from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import ChatOpenAI

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def _project_endpoint() -> str:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.environ.get(
        "AZURE_AI_PROJECT_ENDPOINT"
    )
    if not endpoint:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT is required")
    return endpoint.rstrip("/")


def build_chat_model() -> ChatOpenAI:
    """Use the configured API key, falling back to Azure credentials."""
    api_key = os.environ.get("AZURE_AI_API_KEY")
    if not api_key:
        credential = DefaultAzureCredential()
        api_key = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    return ChatOpenAI(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        base_url=f"{_project_endpoint()}/openai/v1",
        api_key=api_key,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )
