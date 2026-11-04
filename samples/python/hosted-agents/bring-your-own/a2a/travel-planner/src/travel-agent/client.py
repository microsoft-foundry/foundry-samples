# Copyright (c) Microsoft. All rights reserved.
"""Copilot SDK model/tool loop using a Foundry BYOK provider."""

import logging
import os
from contextlib import AsyncExitStack
from time import perf_counter
from urllib.parse import urlsplit

from agents import connect
from azure.ai.agentserver.core import get_request_context
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from copilot import CopilotClient, PermissionHandler, ProviderConfig, ToolSet
from opentelemetry import propagate, trace
from tools import build_tools

logger = logging.getLogger("a2a.travel")


async def ask(instructions: str, message: str) -> tuple[str, list[dict[str, str]]]:
    started = perf_counter()
    request_span = trace.get_current_span().get_span_context()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must use HTTPS")
    headers = get_request_context().platform_headers()
    calls: list[dict[str, str]] = []
    failures: list[str] = []
    async with (
        DefaultAzureCredential(process_timeout=60) as credential,
        AsyncExitStack() as stack,
    ):
        direct_credential: DefaultAzureCredential | ManagedIdentityCredential = (
            credential
        )
        if os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"):
            direct_credential = await stack.enter_async_context(
                ManagedIdentityCredential(
                    client_id=os.environ["FOUNDRY_AGENT_INSTANCE_CLIENT_ID"]
                )
            )
        agents = [
            await connect(os.environ[setting], stack, direct_credential, headers)
            for setting in ("FLIGHT_AGENT_ENDPOINT", "HOTEL_AGENT_ENDPOINT")
        ]
        tools = build_tools(agents, calls, failures)
        propagate.inject(headers)
        token = await credential.get_token("https://ai.azure.com/.default")
        client = CopilotClient()
        await client.start()
        try:
            session = await client.create_session(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                provider=ProviderConfig(
                    type="azure",
                    base_url=endpoint,
                    wire_api="responses",
                    bearer_token=token.token,
                    headers=headers,
                ),
                reasoning_effort="high",
                system_message={"mode": "replace", "content": instructions},
                tools=tools,
                available_tools=ToolSet().add_custom("*"),
                on_permission_request=PermissionHandler.approve_all,
                streaming=False,
                enable_session_store=False,
                enable_config_discovery=False,
                skip_custom_instructions=True,
                enable_skills=False,
            )
            try:
                reply = await session.send_and_wait(message, timeout=300)
                if failures:
                    raise RuntimeError(
                        "Native A2A consultation failed: "
                        + ", ".join(sorted(set(failures)))
                    )
                if reply is None or not reply.data.content:
                    raise RuntimeError("Copilot SDK returned no answer")
                logger.info(
                    "A2A_PLAN_COMPLETED successful_delegations=%s elapsed_ms=%.1f trace_id=%032x",
                    len(calls),
                    (perf_counter() - started) * 1000,
                    request_span.trace_id,
                )
                return reply.data.content, calls
            finally:
                await session.disconnect()
        finally:
            await client.stop()
