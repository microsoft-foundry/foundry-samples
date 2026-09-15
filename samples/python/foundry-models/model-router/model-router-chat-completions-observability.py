"""
Foundry Model Router - Chat Completions Observability Example

This example demonstrates how to use Azure OpenAI's Chat Completions API
with a Foundry Model Router deployment and inspect the selected model,
routing attempts, latency, and status. Model Router automatically
selects the best underlying LLM for each prompt based on your routing mode
(Balanced, Quality, or Cost).

Prerequisites:
  - An Azure OpenAI resource with a "model-router" deployment
    - A .env file beside this script with AZURE_OPENAI_ENDPOINT,
        AZURE_OPENAI_API_KEY, and MODEL_DEPLOYMENT_NAME

Usage:
    pip install -r requirements.txt
    python model-router-chat-completions-observability.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables from .env beside this script
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
api_key = os.environ["AZURE_OPENAI_API_KEY"]
deployment = os.environ["MODEL_DEPLOYMENT_NAME"]

# <response_observability_enable>
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-10-21",
    default_headers={"Foundry-Features": "ModelRouterControls=V1Preview"},
)
# </response_observability_enable>

# <response_observability_request>
response = client.chat.completions.create(
    model=deployment,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": "In one sentence, name the most popular tourist destination in Seattle.",
        },
    ],
)
# </response_observability_request>

print("--- Chat Completions Response ---")
print(f"Response:{response.choices[0].message.content}")
print(
    f"Usage: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion = {response.usage.total_tokens} total tokens"
)

# <response_observability_extract>
print(f"\nRouted to model: {response.model}")
print("--- Model Selection Details ---")
model_selection_details = getattr(response, "model_selection_details", None)
if not model_selection_details:
    print("No model selection details were returned.")
else:
    model_router_details = model_selection_details.get("model_router_details", {})
    print(f"Routing mode: {model_router_details.get('mode', 'unknown')}")

    routing_trace = model_router_details.get("routing_trace", [])
    if not routing_trace:
        print("No routing trace was returned.")

    for decision_number, routing_decision in enumerate(routing_trace, start=1):
        latency_ms = routing_decision.get("latency_ms")
        latency = f"{latency_ms} ms" if latency_ms is not None else "not reported"
        print(f"Routing decision {decision_number} (latency: {latency})")

        for attempt_number, attempt in enumerate(
            routing_decision.get("attempts", []), start=1
        ):
            result = attempt.get("result", {})
            status = result.get("status", "unknown")
            outcome = (
                "selected"
                if isinstance(status, int) and 200 <= status < 300
                else "failed"
            )
            print(
                f"  Attempt {attempt_number}: {attempt.get('model', 'unknown')} - HTTP {status} ({outcome})"
            )

            error = result.get("error")
            if error:
                print(
                    f"    Error: {error.get('code', 'unknown')} - {error.get('message', 'No message')}"
                )
    print("\n")
# </response_observability_extract>
