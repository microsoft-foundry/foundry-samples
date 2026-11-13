"""Use the native A2A 1.0 client with request-scoped platform identity."""

import json
from contextlib import AsyncExitStack
from urllib.parse import urlsplit, urlunsplit

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from azure.core.credentials_async import AsyncTokenCredential
from opentelemetry import propagate


async def send(
    endpoint: str,
    payload: dict,
    context_id: str | None,
    credential: AsyncTokenCredential,
    platform_headers: dict[str, str],
) -> dict:
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("A2A endpoint must be HTTPS or local loopback")
    base = urlunsplit(parsed._replace(query="")).rstrip("/")

    async def authenticate(request: httpx.Request) -> None:
        if request.url.host != parsed.hostname:
            raise ValueError("Agent Card changed the target host")
        if request.url.scheme == "https":
            token = await credential.get_token("https://ai.azure.com/.default")
            request.headers["Authorization"] = "Bearer " + token.token
            request.headers.update(platform_headers)
        request.headers["A2A-Version"] = "1.0"
        propagate.inject(request.headers)

    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(
            httpx.AsyncClient(
                timeout=300,
                event_hooks={"request": [authenticate]},
            )
        )
        card = await A2ACardResolver(http, base).get_agent_card(
            relative_card_path=(
                "agentCard/v1.0?api-version=v1"
                if parsed.scheme == "https"
                else ".well-known/agent-card.json"
            )
        )
        interfaces = [
            item
            for item in card.supported_interfaces
            if item.protocol_binding == "JSONRPC" and item.protocol_version == "1.0"
        ]
        if not interfaces:
            raise RuntimeError("Agent Card has no JSONRPC A2A 1.0 interface")
        interface = interfaces[0]
        if urlsplit(interface.url).hostname != parsed.hostname:
            raise ValueError("Agent Card changed the target host")
        if parsed.scheme == "https":
            if interface.url.split("?")[0].rstrip("/") != base:
                raise ValueError("Agent Card changed the configured Foundry endpoint")
            if not urlsplit(interface.url).query:
                interface.url += "?api-version=v1"
        del card.supported_interfaces[:]
        card.supported_interfaces.append(interface)
        client = await create_client(card, ClientConfig(streaming=False, httpx_client=http))
        stack.push_async_callback(client.close)
        message = new_text_message(json.dumps(payload), role=Role.ROLE_USER)
        if context_id is not None:
            message.context_id = context_id
        tasks = [
            event.task
            async for event in client.send_message(SendMessageRequest(message=message))
            if event.HasField("task")
        ]
        if len(tasks) != 1 or tasks[0].status.state != TaskState.TASK_STATE_COMPLETED:
            raise RuntimeError(f"Expected one completed task, received {tasks!r}")
        task = tasks[0]
        if len(task.artifacts) != 1:
            raise RuntimeError("Expected exactly one diagnostic artifact")
        return {
            "task_id": task.id,
            "context_id": task.context_id,
            "requested_context_id": context_id,
            "receipt": json.loads(get_artifact_text(task.artifacts[0])),
        }
