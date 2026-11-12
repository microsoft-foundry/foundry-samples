# Copyright (c) Microsoft. All rights reserved.

# <doc_hosted_agent_contract_responses_protocol_example>
# <doc_add_protocol_adapter_responses_protocol>
"""Hello World — Bring Your Own Responses agent.

Forwards user input to a Foundry model via the Responses API and streams
the reply back through the Responses protocol. See README.md for setup.
"""

import asyncio
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)
logger = logging.getLogger(__name__)

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

_responses_client = AIProjectClient(
    endpoint=_endpoint, credential=DefaultAzureCredential()
).get_openai_client().responses

app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)

_SYSTEM_PROMPT = "You are a helpful AI assistant. Be concise and informative."

_ROLE_MAP = {"output_text": "assistant", "input_text": "user"}

def _build_input(current_input: str, history: list) -> list[dict]:
    """Convert platform history + current message into Responses API input."""
    items = []
    for item in history:
        for content in item.get("content") or []:
            role = _ROLE_MAP.get(content.get("type"))
            text = content.get("text")
            if role and text:
                items.append({"role": role, "content": text})
    items.append({"role": "user", "content": current_input})
    return items


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    """Forward user input to the model with conversation history."""
    user_input = await context.get_input_text() or "Hello!"
    history = await context.get_history()
    input_items = _build_input(user_input, history)

    response = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _responses_client.create(
            model=_model,
            instructions=_SYSTEM_PROMPT,
            input=input_items,
            store=False,
        ),
    )

    return TextResponse(context, request, text=response.output_text)


app.run()
# </doc_add_protocol_adapter_responses_protocol>
# </doc_hosted_agent_contract_responses_protocol_example>
