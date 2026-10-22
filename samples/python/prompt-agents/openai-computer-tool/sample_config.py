"""Shared configuration and client helpers for the OpenAI Computer Tool Prompt Agent sample.

Follows the `sample_config.py` pattern used across `samples/python/prompt-agents/`:
- Owns the default `AGENT_NAME` and path to `agents/computer_agent/instructions.md`.
- Resolves `AZURE_AI_PROJECT_ENDPOINT` (or `PROJECT_ENDPOINT`) and `AZURE_AI_MODEL_DEPLOYMENT_NAME`
  (or `MODEL_DEPLOYMENT_NAME`).
"""

import os
from pathlib import Path

import dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

ROOT_DIR = Path(__file__).resolve().parent
dotenv.load_dotenv(ROOT_DIR / ".env")
INSTRUCTIONS_PATH = ROOT_DIR / "agents" / "computer_agent" / "instructions.md"

AGENT_NAME = os.environ.get("AGENT_NAME", "openai-computer-agent")


def load_agent_instructions() -> str:
    """Load the generic Prompt Agent system instructions from `agents/computer_agent/instructions.md`."""
    return INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()


def get_project_endpoint() -> str:
    """Resolve the Azure AI Foundry project endpoint from environment variables."""
    endpoint = (
        os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        or os.environ.get("PROJECT_ENDPOINT")
        or os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        or ""
    ).rstrip("/")
    if not endpoint:
        raise RuntimeError(
            "Set AZURE_AI_PROJECT_ENDPOINT (or PROJECT_ENDPOINT) in .env or via `azd env set`."
        )
    return endpoint


def get_model_deployment_name() -> str:
    """Resolve the model deployment name supporting the GA OpenAI Computer Tool (`computer`)."""
    return (
        os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.environ.get("MODEL_DEPLOYMENT_NAME")
        or os.environ.get("FOUNDRY_MODEL")
        or "gpt-5.4"
    )


def get_project_client() -> AIProjectClient:
    """Create an authenticated `AIProjectClient` using `DefaultAzureCredential`."""
    return AIProjectClient(
        endpoint=get_project_endpoint(),
        credential=DefaultAzureCredential(),
    )
