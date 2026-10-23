# Copyright (c) Microsoft. All rights reserved.

"""Shared configuration and client helpers for the OpenAI Computer Tool Hosted Agent sample."""

import os
from pathlib import Path

import dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

SRC_DIR = Path(__file__).resolve().parent.parent
SAMPLE_ROOT_DIR = SRC_DIR.parent.parent

dotenv.load_dotenv(SRC_DIR / ".env", override=False)
dotenv.load_dotenv(SAMPLE_ROOT_DIR / ".env", override=False)

PROMPTS_PATH = SRC_DIR / "prompts" / "base.md"


def load_agent_instructions() -> str:
    """Load the desktop automation system instructions from `prompts/base.md`."""
    return PROMPTS_PATH.read_text(encoding="utf-8").strip()


def get_project_endpoint() -> str:
    """Resolve the Microsoft Foundry project endpoint from environment variables."""
    endpoint = (
        os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        or ""
    ).rstrip("/")
    if not endpoint:
        raise RuntimeError(
            "Set FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT in .env or via `azd env set`."
        )
    return endpoint


def get_model_deployment_name() -> str:
    """Resolve the model deployment name supporting the GA OpenAI Computer Tool (`computer`)."""
    return os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4")


def get_project_client() -> AIProjectClient:
    """Create an authenticated `AIProjectClient` using `DefaultAzureCredential`."""
    return AIProjectClient(
        endpoint=get_project_endpoint(),
        credential=DefaultAzureCredential(),
    )
