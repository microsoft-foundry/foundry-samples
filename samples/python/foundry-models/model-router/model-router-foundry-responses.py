"""
Foundry Model Router - Foundry Responses SDK (AIProjectClient) Example

This example demonstrates how to use the Azure AI Projects SDK
(AIProjectClient) to get an authenticated OpenAI client and call the
Responses API with a Foundry Model Router deployment.

NOTE: AIProjectClient requires Entra ID authentication (DefaultAzureCredential),
      not API keys. You must be logged in via `az login` before running this.

Prerequisites:
  - An Azure AI Foundry project with a "model-router" deployment
  - Azure CLI installed and logged in (`az login`)
  - A .env file in the repo root with AZURE_AI_PROJECT_ENDPOINT and
    MODEL_DEPLOYMENT_NAME

Usage:
  pip install -r requirements.txt
  az login
  python model-router-foundry-responses-sdk.py
"""

# <doc_responses_model_routing_call_models_through_the_responses_api>
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env beside this script
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
deployment = os.environ["MODEL_DEPLOYMENT_NAME"]

# <foundry_responses>
with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=project_endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    response = openai_client.responses.create(
        model=deployment,
        input="In one sentence, name the most popular tourist destination in Seattle.",
    )
    # </foundry_responses>

    print("--- Foundry Responses SDK Output ---")
    print(f"Routed to model: {response.model}")
    print(f"Response:\n{response.output_text}")
    print(
        f"\nUsage: {response.usage.input_tokens} input + {response.usage.output_tokens} output = {response.usage.total_tokens} total tokens"
    )
# </doc_responses_model_routing_call_models_through_the_responses_api>
