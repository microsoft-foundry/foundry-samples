# Copyright (c) Microsoft. All rights reserved.
"""Copilot SDK model/tool loop using a Foundry BYOK provider."""

import os
from urllib.parse import urlsplit

from azure.ai.agentserver.core import get_request_context
from azure.identity.aio import DefaultAzureCredential
from copilot import CopilotClient, PermissionHandler, ProviderConfig, ToolSet
from opentelemetry import propagate


async def ask(instructions: str, message: str) -> str:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must use HTTPS")
    headers = get_request_context().platform_headers()
    propagate.inject(headers)
    async with DefaultAzureCredential(process_timeout=60) as credential:
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
                available_tools=ToolSet(),
                on_permission_request=PermissionHandler.approve_all,
                streaming=False,
                enable_session_store=False,
                enable_config_discovery=False,
                skip_custom_instructions=True,
                enable_skills=False,
            )
            try:
                reply = await session.send_and_wait(message, timeout=300)
                if reply is None or not reply.data.content:
                    raise RuntimeError("Copilot SDK returned no answer")
                return reply.data.content
            finally:
                await session.disconnect()
        finally:
            await client.stop()
