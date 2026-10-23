"""Shared configuration and client helpers for the OpenAI Computer Tool Prompt Agent sample."""

import os
from pathlib import Path

import dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

SRC_DIR = Path(__file__).resolve().parent.parent
SAMPLE_ROOT_DIR = SRC_DIR.parent.parent

dotenv.load_dotenv(SRC_DIR / ".env")
dotenv.load_dotenv(SAMPLE_ROOT_DIR / ".env")

PROMPTS_PATH = SRC_DIR / "prompts" / "base.md"
AGENT_NAME = os.environ.get("AGENT_NAME", "openai-computer-agent")


def load_agent_instructions() -> str:
    """Load the generic Prompt Agent system instructions from `prompts/base.md`."""
    return PROMPTS_PATH.read_text(encoding="utf-8").strip()


def get_project_endpoint() -> str:
    """Resolve the Azure AI Foundry project endpoint from environment variables."""
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        raise RuntimeError(
            "Set AZURE_AI_PROJECT_ENDPOINT in .env or via `azd env set`."
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
