# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Serve a minimal LangChain graph with the sample's existing locked dependencies."""

# <doc_langchain_hosted_agents_create_a_responses_host>
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_azure_ai.agents.hosting import ResponsesHostServer

logger = logging.getLogger(__name__)
AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def build_chat_model(credential) -> ChatOpenAI:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    model_name = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-4.1")

    # Derive the OpenAI-compatible URL without retaining an unused project client.
    with (
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
        project.get_openai_client() as openai,
    ):
        base_url = str(openai.base_url)

    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=get_bearer_token_provider(credential, AZURE_AI_SCOPE),
    )


def main() -> None:
    # Keep the credential available while the host serves model requests.
    with DefaultAzureCredential() as credential:
        graph = create_agent(build_chat_model(credential), tools=[])
        host = ResponsesHostServer(graph)
        logger.info("langchain_host_starting")
        host.run(
            host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "8088")),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
# </doc_langchain_hosted_agents_create_a_responses_host>
