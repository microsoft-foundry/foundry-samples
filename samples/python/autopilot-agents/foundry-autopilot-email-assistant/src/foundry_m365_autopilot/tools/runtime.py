# Copyright (c) Microsoft. All rights reserved.

"""Runtime dependencies injected into local Responses API function tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

import httpx
from microsoft_agents.hosting.core import Authorization, TurnContext


class MailMonitoringStore(Protocol):
    async def get(self, tenant_id: str, agent_user_id: str) -> Optional[dict[str, Any]]: ...

    async def save(
        self,
        tenant_id: str,
        agent_user_id: str,
        manager: dict[str, str],
        source_text: str,
        filter_expression: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def disable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]: ...

    async def enable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]: ...

    async def get_manager_conversation(
        self, tenant_id: str, agent_user_id: str
    ) -> Optional[dict[str, Any]]: ...

    async def save_manager_conversation(
        self,
        tenant_id: str,
        agent_user_id: str,
        conversation: dict[str, Any],
    ) -> None: ...


@dataclass
class ToolRuntime:
    """Narrow dependency boundary shared by local function tools."""

    auth: Authorization
    auth_handler_name: Optional[str]
    context: TurnContext
    http_client: httpx.AsyncClient
    mail_monitor_store: MailMonitoringStore
    manager_cache: dict[str, tuple[float, dict[str, str]]]
