"""Sample 10 - configuration-driven Responses API host.

Defines a no-tool ``create_agent`` graph that is exported for use by
``langchain_azure_ai.agents.hosting.run``. The hosting entrypoint loads the
compiled graph from ``langgraph.json`` and exposes it over the Responses
protocol.

Required environment variables (set in `.env` or your shell):

    FOUNDRY_PROJECT_ENDPOINT        e.g. https://<acct>.services.ai.azure.com/api/projects/<proj>
    AZURE_AI_MODEL_DEPLOYMENT_NAME  e.g. gpt-5.4-mini (defaults to "gpt-5.4-mini")
    PORT                            optional, defaults to 8088

Run::

    az login
    cp .env.example .env  # then edit the values
    python -m langchain_azure_ai.agents.hosting.run --protocol responses

Then in another terminal:

    curl -N -X POST http://127.0.0.1:8088/responses \
      -H 'Content-Type: application/json' \
            -d '{"input":"Hello!","stream":true}'
"""
from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME") or "gpt-5.4-mini"
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


graph = create_agent(_build_chat_model(), tools=[])
