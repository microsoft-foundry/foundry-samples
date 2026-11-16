# Copyright (c) Microsoft. All rights reserved.

"""Getting-started: GitHub Copilot SDK with the Foundry invocations protocol.

Supports two auth modes selected automatically by environment variables:
  - GITHUB_TOKEN set → uses the GitHub Copilot model (quickest start)
  - FOUNDRY_PROJECT_ENDPOINT + AZURE_AI_MODEL_DEPLOYMENT_NAME set
        → uses a BYOK Foundry model via Managed Identity (no token needed)
"""

import asyncio
import json
import logging
import os
import pathlib
import sys
import uuid

from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse


from azure.ai.agentserver.invocations import InvocationAgentServerHost
from copilot import CopilotClient, PermissionHandler, ProviderConfig
from copilot.session_events import SessionEventType

load_dotenv(override=False)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = InvocationAgentServerHost()

_client: CopilotClient | None = None
_session = None
_session_id: str | None = None
_skills_dir = str(pathlib.Path(__file__).parent / "skills")


# ── BYOK helpers ─────────────────────────────────────────────────────────────


def _byok_provider() -> tuple[ProviderConfig | None, str | None]:
    """Return (provider, model) for BYOK mode, or (None, None) for Copilot mode.

    Uses the FOUNDRY_PROJECT_ENDPOINT directly as a project-level OpenAI
    endpoint (e.g. https://<resource>.services.ai.azure.com/api/projects/<proj>/openai/v1).
    """
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
    if not endpoint or not model:
        return None, None

    from azure.identity import DefaultAzureCredential
    token = DefaultAzureCredential().get_token(
        "https://ai.azure.com/.default"
    ).token

    provider = ProviderConfig(
        type="azure",
        base_url=endpoint,
        wire_api="responses",
        bearer_token=token,
    )
    return provider, model


# ── Session management ───────────────────────────────────────────────────────


async def _ensure_session():
    """Resume a persisted session or create a new one (lazy, runs once)."""
    global _client, _session, _session_id
    if _session is not None:
        return

    _session_id = os.environ.get("FOUNDRY_AGENT_SESSION_ID")
    if not _session_id:
        _session_id = str(uuid.uuid4())
        logger.warning(
            "FOUNDRY_AGENT_SESSION_ID not set, using: %s", _session_id)

    github_token = os.environ.get("GITHUB_TOKEN")
    # Token acquisition is blocking I/O; keep it off the event loop.
    provider, model = await asyncio.to_thread(_byok_provider)

    if provider:
        # BYOK mode: Foundry model via Managed Identity — no token needed.
        _client = CopilotClient()
    elif github_token:
        # Copilot mode: use GitHub token.
        _client = CopilotClient(github_token=github_token)
    else:
        raise RuntimeError(
            "Set GITHUB_TOKEN (Copilot model) or "
            "FOUNDRY_PROJECT_ENDPOINT + AZURE_AI_MODEL_DEPLOYMENT_NAME "
            "(BYOK Foundry model)")
    await _client.start()

    working_dir = str(pathlib.Path.home())

    common = dict(
        on_permission_request=PermissionHandler.approve_all,
        streaming=True,
        skill_directories=[_skills_dir],
        working_directory=working_dir,
        provider=provider,
        model=model,
    )

    try:
        _session = await _client.resume_session(_session_id, **common)
        logger.info("Resumed session: %s", _session_id)
    except Exception:
        _session = await _client.create_session(session_id=_session_id, **common)
        logger.info("Created session: %s", _session_id)


async def _stream_response(invocation_id: str, input_text: str):
    """Forward Copilot SDK session events as SSE."""
    await _ensure_session()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(event):
        if event.type == SessionEventType.SESSION_IDLE:
            queue.put_nowait(None)
        elif event.type == SessionEventType.SESSION_ERROR:
            queue.put_nowait(RuntimeError(
                getattr(event.data, "message", "error")))
        else:
            queue.put_nowait(event)

    unsubscribe = _session.on(on_event)
    try:
        await _session.send(input_text)
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n".encode()
                break
            yield f"data: {json.dumps(item.to_dict())}\n\n".encode()

        yield f"event: done\ndata: {json.dumps({'invocation_id': invocation_id, 'session_id': _session_id})}\n\n".encode()
    finally:
        unsubscribe()


@app.invoke_handler
async def handle_invoke(request: Request) -> Response:
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("body is not a JSON object")
        input_text = data.get("input")
        if not isinstance(input_text, str) or not input_text.strip():
            raise ValueError('missing or empty "input" field')
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "message": (
                    'Request body must be a JSON object with a non-empty "input" string, '
                    'e.g. {"input": "What can you help me with?"}'
                ),
            },
        )
    return StreamingResponse(
        _stream_response(request.state.invocation_id, input_text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


if __name__ == "__main__":
    has_token = bool(os.environ.get("GITHUB_TOKEN"))
    has_byok = bool(
        os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        and os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    )
    if not has_token and not has_byok:
        sys.exit(
            "Error: Set GITHUB_TOKEN (Copilot model) or "
            "FOUNDRY_PROJECT_ENDPOINT + AZURE_AI_MODEL_DEPLOYMENT_NAME "
            "(BYOK Foundry model)")
    app.run()
