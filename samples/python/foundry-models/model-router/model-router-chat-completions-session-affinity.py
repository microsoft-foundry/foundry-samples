"""
Foundry Model Router - Chat Completions Session Affinity Example

This example demonstrates how to use one session ID across separate
Chat Completions requests so Model Router can keep using the associated
eligible model while preserving normal fallback behavior.

Prerequisites:
  - An Azure OpenAI resource with a "model-router" deployment
  - A .env file beside this script with AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY, and MODEL_DEPLOYMENT_NAME

Usage:
    pip install -r requirements.txt
    python model-router-chat-completions-session-affinity.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
api_key = os.environ["AZURE_OPENAI_API_KEY"]
deployment = os.environ["MODEL_DEPLOYMENT_NAME"]

# <session_affinity_enable>
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-10-21",
    default_headers={"Foundry-Features": "ModelRouterControls=V1Preview"},
)

# Use an opaque application-owned ID without secrets or personal information.
# A fresh value makes the first request in each run establish a new association.
session_id = f"trip-planner-{uuid.uuid4()}"
session_affinity = {
    "routing_config": {
        "session_affinity": {
            "mode": "sticky",
            "session_id": session_id,
        }
    }
}
# </session_affinity_enable>

messages = [
    {"role": "system", "content": "You are a helpful travel planner."},
    {"role": "user", "content": "Plan a one-day family trip to Seattle."},
]

# <session_affinity_invoke>
first_response = client.chat.completions.create(
    model=deployment,
    messages=messages,
    extra_body=session_affinity,
)
# </session_affinity_invoke>

messages.extend(
    [
        {"role": "assistant", "content": first_response.choices[0].message.content},
        {
            "role": "user",
            "content": "Add restaurant suggestions and indoor activities.",
        },
    ]
)

second_response = client.chat.completions.create(
    model=deployment,
    messages=messages,
    extra_body=session_affinity,
)

def print_response(turn, response):
    print(f"\n--- {turn} ---")
    print(f"Serving model: {response.model}")

    model_selection_details = getattr(response, "model_selection_details", None)
    if not model_selection_details:
        print("No model selection details were returned.")
    else:
        model_router_details = model_selection_details.get("model_router_details", {})

        # <session_affinity_extract>
        affinity_details = model_router_details.get("session_affinity")
        if not affinity_details:
            print("No session affinity details were returned.")
        else:
            print(f"Affinity mode: {affinity_details.get('mode', 'unknown')}")
            print(f"Affinity source: {affinity_details.get('source', 'unknown')}")
            print(f"Affinity decision: {affinity_details.get('decision', 'not reported')}")
        # </session_affinity_extract>

    print(f"Response:\n{response.choices[0].message.content}")

print_response("First turn", first_response)
print_response("Second turn", second_response)