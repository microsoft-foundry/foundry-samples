# Copyright (c) Microsoft. All rights reserved.
"""Copilot SDK model/tool loop using a Foundry BYOK provider."""

import logging
import os
from contextlib import AsyncExitStack
from time import perf_counter
from urllib.parse import urlsplit

from agents import connect
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.core.storage import FoundryStateStore
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from copilot import CopilotClient, PermissionHandler, ProviderConfig, ToolSet
from opentelemetry import propagate, trace
from plan_store import INSTRUCTIONS as STORE_INSTRUCTIONS
from plan_store import build_tools as build_store_tools
from plan_store import failure_message, validate_completion
from tools import build_tools

logger = logging.getLogger("a2a.travel")


async def ask(instructions: str, message: str, *, evidence: dict) -> tuple[str, dict]:
    started = perf_counter()
    request_span = trace.get_current_span().get_span_context()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must use HTTPS")
    caller = get_request_context()
    hosted = bool(os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"))
    if hosted and not (caller.call_id or caller.user_id):
        raise PermissionError("Hosted trip storage requires trusted caller context")
    headers = caller.platform_headers()
    calls: list[dict[str, str]] = []
    research_context: dict[str, str] = {}
    failures: list[str] = []
    operations = []
    failed_calls: list[dict[str, str]] = []
    evidence.update(
        specialist_calls=calls,
        specialist_failures=failed_calls,
        state_store={
            "store": os.environ.get("TRAVEL_PLAN_STORE_NAME", "travel-web-research"),
            "backend": "foundry" if hosted else "local-file",
            "operations": operations,
        },
    )
    async with (
        DefaultAzureCredential(process_timeout=60) as credential,
        AsyncExitStack() as stack,
    ):
        direct_credential: DefaultAzureCredential | ManagedIdentityCredential = (
            credential
        )
        if hosted:
            direct_credential = await stack.enter_async_context(
                ManagedIdentityCredential(
                    client_id=os.environ["FOUNDRY_AGENT_INSTANCE_CLIENT_ID"]
                )
            )
        agents = [
            await connect(
                os.environ[setting],
                stack,
                direct_credential,
                headers,
                version=os.environ.get(setting.replace("_ENDPOINT", "_VERSION")),
            )
            for setting in ("FLIGHT_AGENT_ENDPOINT", "HOTEL_AGENT_ENDPOINT")
        ]
        tools = build_tools(
            agents,
            calls,
            failures,
            research_context=research_context,
            failed_calls=failed_calls,
        )
        store = await FoundryStateStore.get_or_create(
            os.environ.get("TRAVEL_PLAN_STORE_NAME", "travel-web-research"),
            credential=credential,
            user_isolation=True,
            user_id=caller.user_id,
            item_ttl_seconds=30 * 24 * 60 * 60,
            description="Saved public trip research, unverified recommendations, metadata and history",
        )
        await stack.enter_async_context(store)
        if (await store.get()).user_isolation is not True:
            raise PermissionError("Travel plans require a user-isolated state store")
        tools += build_store_tools(
            store,
            operations,
            calls,
            failures,
            call_id=caller.call_id,
            specialist_tools={tool.name for tool in tools},
            research_context=research_context,
        )
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
                system_message={
                    "mode": "replace",
                    "content": instructions + STORE_INSTRUCTIONS,
                },
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
                try:
                    reply = await session.send_and_wait(message, timeout=600)
                except Exception as error:
                    raise RuntimeError(
                        str(error)
                        + ". "
                        + failure_message([type(error).__name__], operations)
                    ) from error
                if failures:
                    raise RuntimeError(failure_message(failures, operations))
                if reply is None or not reply.data.content:
                    raise RuntimeError("Copilot SDK returned no answer")
                validate_completion(operations, calls)
                logger.info(
                    "A2A_PLAN_COMPLETED successful_delegations=%s elapsed_ms=%.1f trace_id=%032x",
                    len(calls),
                    (perf_counter() - started) * 1000,
                    request_span.trace_id,
                )
                return reply.data.content, evidence
            finally:
                await session.disconnect()
        finally:
            await client.stop()
