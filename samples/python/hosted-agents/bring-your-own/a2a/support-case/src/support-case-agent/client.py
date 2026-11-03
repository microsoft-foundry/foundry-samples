# Copyright (c) Microsoft. All rights reserved.
"""Fresh Copilot sessions with persistent, user-isolated support-case tools."""

import os
from urllib.parse import urlsplit

from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.core.storage import FoundryStateStore
from azure.identity.aio import DefaultAzureCredential
from copilot import CopilotClient, PermissionHandler, ProviderConfig, ToolSet
from tools import build_tools

INSTRUCTIONS = """You manage synthetic support cases using persistent state-store tools.
You have no conversation memory between requests. Always use get_case or list_cases
to retrieve saved facts; never pretend to remember a case.
For a new case use open_case and return its exact generated case ID.
For findings use add_finding, preserving the user's observations without inventing evidence.
For case history call get_case and report its saved events and version.
When asked for a resolution summary, first call get_case, summarize the description
and accumulated findings, distinguish observed facts from proposed next steps, then
call save_resolution_summary with that version and your summary text.
Do not claim any creation, finding or summary was saved until its tool succeeds.
If a tool fails, explain the failure. Do not turn a failed write into a success.
On a concurrency conflict reread the case; never blindly overwrite newer data.
Do not automatically repeat writes. If a case ID is missing, list cases or ask.
All cases are synthetic. Do not contact customers, change infrastructure or claim
a real incident is resolved. Reply concisely in Markdown and show the case ID,
saved version and requested history/summary. No shell, file or external tools."""


async def ask(message: str) -> tuple[str, dict]:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must use HTTPS")
    context = get_request_context()
    hosted = bool(os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"))
    if hosted and not (context.call_id or context.user_id):
        raise PermissionError("Hosted case storage requires trusted caller context")
    operations = []
    async with DefaultAzureCredential(process_timeout=60) as credential:
        store = await FoundryStateStore.get_or_create(
            os.environ.get("CASE_STORE_NAME", "support-cases"),
            credential=credential,
            user_isolation=True,
            item_ttl_seconds=30 * 24 * 60 * 60,
            description="Synthetic support case records and history",
        )
        async with store:
            if (await store.get()).user_isolation is not True:
                raise PermissionError(
                    "Support cases require a user-isolated state store"
                )
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
                        headers=context.platform_headers(),
                    ),
                    reasoning_effort="high",
                    system_message={"mode": "replace", "content": INSTRUCTIONS},
                    tools=build_tools(store, operations, call_id=context.call_id),
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
                    if reply is None or not reply.data.content:
                        raise RuntimeError("Copilot SDK returned no answer")
                    return reply.data.content, {
                        "store": store.name,
                        "backend": "foundry" if hosted else "local-file",
                        "operations": operations,
                    }
                finally:
                    await session.disconnect()
            finally:
                await client.stop()
