# Copyright (c) Microsoft. All rights reserved.
"""Authenticated Agent Card discovery and native A2A client construction."""

import logging
import os
from contextlib import AsyncExitStack
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx
from a2a.client import A2ACardResolver, Client, ClientConfig, create_client
from a2a.types import AgentCard
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from opentelemetry import propagate, trace

logger = logging.getLogger("a2a.travel.agents")


def trusted_url(url: str, project: str) -> None:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or "%" in parsed.path:
        raise ValueError(
            "Agent URL contains credentials, a fragment or an encoded path"
        )
    if any(segment in {".", ".."} for segment in parsed.path.split("/")):
        raise ValueError("Agent URL contains path traversal")
    if parsed.scheme == "https" and url.startswith(project.rstrip("/") + "/agents/"):
        return
    if (
        not os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT")
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        return
    raise ValueError(
        "Agent URL must be in the configured Foundry project (or loopback locally)"
    )


async def connect(
    endpoint: str,
    stack: AsyncExitStack,
    credential: DefaultAzureCredential | ManagedIdentityCredential,
    platform_headers: dict[str, str],
    *,
    version: str | None = None,
) -> tuple[AgentCard, Client]:
    project = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    trusted_url(endpoint, project)
    if version is not None and (
        not version.isascii() or not version.isdigit() or int(version) < 1
    ):
        raise ValueError("Specialist version must be a positive integer")
    endpoint = urlunsplit(urlsplit(endpoint)._replace(query="")).rstrip("/")
    started = perf_counter()
    request_span = trace.get_current_span().get_span_context()

    async def authenticate(request: httpx.Request) -> None:
        trusted_url(str(request.url), project)
        if request.url.scheme == "https":
            token = await credential.get_token("https://ai.azure.com/.default")
            request.headers["Authorization"] = "Bearer " + token.token
            request.headers.update(platform_headers)
            if version is not None:
                request.headers["x-agent-version-override"] = version
        request.headers["A2A-Version"] = "1.0"
        propagate.inject(request.headers)
        request.extensions["a2a_started_at"] = perf_counter()
        active_span = trace.get_current_span().get_span_context()
        logger.info(
            "A2A_HTTP_REQUEST method=%s target=%s trace_id=%032x "
            "parent_span_id=%016x trace_header_present=%s",
            request.method,
            request.url.path,
            active_span.trace_id,
            active_span.span_id,
            "traceparent" in request.headers,
        )

    async def report_failure(response: httpx.Response) -> None:
        if response.is_error:
            logger.error(
                "A2A_HTTP_FAILED status=%s target=%s request_id=%s "
                "elapsed_ms=%.1f trace_id=%032x",
                response.status_code,
                response.request.url.path,
                response.headers.get("x-request-id", ""),
                (perf_counter() - response.request.extensions["a2a_started_at"]) * 1000,
                trace.get_current_span().get_span_context().trace_id,
            )
            if (
                response.status_code == 404
                and "agentCard/" in response.request.url.path
            ):
                raise RuntimeError(
                    "Agent Card discovery returned HTTP 404. Verify the specialist "
                    "endpoint and the planner instance identity's Foundry Agent Consumer "
                    "access at project scope. A 404 can mask authorization failure; "
                    "negative authorization decisions were observed cached for five "
                    "minutes. Allow role propagation/cache expiry before retrying."
                )

    http = await stack.enter_async_context(
        httpx.AsyncClient(
            timeout=240,
            event_hooks={"request": [authenticate], "response": [report_failure]},
        )
    )
    path = (
        "agentCard/v1.0?api-version=v1"
        if endpoint.startswith("https:")
        else ".well-known/agent-card.json"
    )
    try:
        card = await A2ACardResolver(http, endpoint).get_agent_card(
            relative_card_path=path
        )
        interfaces = [
            interface
            for interface in card.supported_interfaces
            if interface.protocol_binding == "JSONRPC"
            and interface.protocol_version == "1.0"
        ]
        if not card.name or not card.skills or not interfaces:
            raise ValueError(
                "Agent Card has no name, skills or JSONRPC A2A 1.0 interface"
            )
        interface = interfaces[0]
        trusted_url(interface.url, project)
        if urlsplit(interface.url).scheme != urlsplit(endpoint).scheme:
            raise ValueError("Agent Card changed the configured transport scheme")
        if interface.url.startswith("https:") and not urlsplit(interface.url).query:
            interface.url += "?api-version=v1"
        del card.supported_interfaces[:]
        card.supported_interfaces.append(interface)
        client = await create_client(
            card, ClientConfig(streaming=False, httpx_client=http)
        )
        stack.push_async_callback(client.close)
    except Exception as error:
        logger.error(
            "A2A_CARD_DISCOVERY_FAILED error_type=%s elapsed_ms=%.1f trace_id=%032x",
            type(error).__name__,
            (perf_counter() - started) * 1000,
            request_span.trace_id,
        )
        raise
    logger.info(
        "A2A_CARD_DISCOVERED agent=%s protocol=%s version=%s elapsed_ms=%.1f trace_id=%032x",
        card.name,
        interface.protocol_binding,
        interface.protocol_version,
        (perf_counter() - started) * 1000,
        request_span.trace_id,
    )
    return card, client
