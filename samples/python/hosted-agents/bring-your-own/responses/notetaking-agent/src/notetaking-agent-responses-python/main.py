# Copyright (c) Microsoft. All rights reserved.

"""Note-taking agent using azure-ai-agentserver-responses with Azure OpenAI.

Uses the Azure OpenAI Responses API with function calling to understand user
intent (save/get notes) and streams responses via the Responses protocol.
Notes are persisted per session in JSONL files accessible via the Session
Files API.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (auto-injected by the platform)
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name (e.g., gpt-4o)

Usage::

    # Set environment variables
    export FOUNDRY_PROJECT_ENDPOINT="https://your-resource.openai.azure.com/"
    export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"

    # Start the agent
    python main.py

    # Save a note
    curl -N -X POST http://localhost:8088/responses \\
        -H "Content-Type: application/json" \\
        -d '{"input": "save a note - book reservation for dinner", "stream": true, "agent_session_id": "my-session"}'

    # Get all notes
    curl -N -X POST http://localhost:8088/responses \\
        -H "Content-Type: application/json" \\
        -d '{"input": "get all my notes", "stream": true, "agent_session_id": "my-session"}'
"""

import asyncio
import json
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
)

import note_store

logger = logging.getLogger(__name__)

if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.warning(
        "APPLICATIONINSIGHTS_CONNECTION_STRING not set — traces will not be sent to "
        "Application Insights. Set it to enable local telemetry. "
        "(This variable is auto-injected in hosted Foundry containers — do not declare it in agent.manifest.yaml.)"
    )

# ── Configuration ─────────────────────────────────────────────────────────────

FOUNDRY_PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
if not FOUNDRY_PROJECT_ENDPOINT:
    raise EnvironmentError(
        "FOUNDRY_PROJECT_ENDPOINT environment variable is not set. "
        "Set it to your Foundry project endpoint, or use 'azd ai agent run'."
    )

AZURE_AI_MODEL_DEPLOYMENT_NAME = os.environ.get(
    "AZURE_AI_MODEL_DEPLOYMENT_NAME")
if not AZURE_AI_MODEL_DEPLOYMENT_NAME:
    raise EnvironmentError(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable is not set. "
        "Set it to your model deployment name as declared in agent.manifest.yaml."
    )

_credential = DefaultAzureCredential()
_project_client = AIProjectClient(
    endpoint=FOUNDRY_PROJECT_ENDPOINT, credential=_credential)

# Use the Responses API — not chat.completions (Chat Completions API is legacy).
_openai_client = _project_client.get_openai_client()

# Tool definitions for Azure OpenAI Responses API
TOOLS = [
    {
        "type": "function",
        "name": "save_note",
        "description": "Save a note with the current timestamp. Use this when the user asks to save, add, or create a note.",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note text to save",
                }
            },
            "required": ["note"],
        },
    },
    {
        "type": "function",
        "name": "get_notes",
        "description": "Retrieve all saved notes. Use this when the user asks to get, list, show, or view their notes.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]

SYSTEM_PROMPT = (
    "You are a helpful note-taking assistant. You can save notes and retrieve them. "
    "When the user asks to save a note, extract the note content and call save_note. "
    "When the user asks to see their notes, call get_notes. "
    "Always respond in a friendly, concise manner."
)


def _execute_tool_call(function_name: str, arguments: str, session_id: str) -> str:
    """Execute a tool call and return the result as JSON."""
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid tool arguments: {e}"})

    if function_name == "save_note":
        note_text = args.get("note")
        if not note_text:
            return json.dumps({"error": "Missing required 'note' argument"})
        entry = note_store.save_note(session_id, note_text)
        return json.dumps({"status": "saved", "note": entry.note, "timestamp": entry.timestamp})
    elif function_name == "get_notes":
        notes = note_store.get_notes(session_id)
        return json.dumps({
            "count": len(notes),
            "notes": [{"note": n.note, "timestamp": n.timestamp} for n in notes],
        })
    return json.dumps({"error": f"Unknown function: {function_name}"})


app = ResponsesAgentServerHost()


@app.response_handler
async def handle_create(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    """Handle note-taking requests with Azure OpenAI Responses API."""
    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )

    yield stream.emit_created()
    yield stream.emit_in_progress()

    user_input = await context.get_input_text() or ""
    # Hosted sessions may omit agent_session_id from the body; the platform
    # supplies the session ID through FOUNDRY_AGENT_SESSION_ID instead.
    session_id = (
        request.get("agent_session_id")
        or os.environ.get("FOUNDRY_AGENT_SESSION_ID")
        or "default"
    )

    # Emit output item structure before streaming content
    message_item = stream.add_output_item_message()
    yield message_item.emit_added()

    text_content = message_item.add_text_content()
    yield text_content.emit_added()

    full_text = ""

    try:
        loop = asyncio.get_event_loop()

        # First call — determine if tool calls are needed
        response = await loop.run_in_executor(
            None,
            lambda: _openai_client.responses.create(
                model=AZURE_AI_MODEL_DEPLOYMENT_NAME,
                instructions=SYSTEM_PROMPT,
                input=user_input,
                tools=TOOLS,
            ),
        )

        # Check if there are function_call output items
        function_calls = [
            item for item in response.output
            if item.type == "function_call"
        ]

        if function_calls:
            # Execute tool calls and build follow-up input
            follow_up_input = []
            # Include the function_call items from the response
            for fc in function_calls:
                follow_up_input.append(fc)
                result = _execute_tool_call(fc.name, fc.arguments, session_id)
                follow_up_input.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

            # Second call — stream the final response with tool results
            openai_stream = await loop.run_in_executor(
                None,
                lambda: _openai_client.responses.create(
                    model=AZURE_AI_MODEL_DEPLOYMENT_NAME,
                    instructions=SYSTEM_PROMPT,
                    input=follow_up_input,
                    stream=True,
                ),
            )

            for event in openai_stream:
                if cancellation_signal.is_set():
                    yield stream.emit_incomplete("cancelled")
                    return
                if event.type == "response.output_text.delta":
                    full_text += event.delta
                    yield text_content.emit_delta(event.delta)
        else:
            # No tool calls — extract text from the first response directly
            for item in response.output:
                if item.type == "message":
                    for part in item.content:
                        if part.type == "output_text":
                            full_text += part.text
            if full_text:
                yield text_content.emit_delta(full_text)

    except Exception as e:
        if not full_text:
            full_text = f"Error calling Azure OpenAI: {e}"
            yield text_content.emit_delta(full_text)

    yield text_content.emit_text_done()
    yield text_content.emit_done()
    yield message_item.emit_done()

    yield stream.emit_completed()


if __name__ == "__main__":
    app.run()
