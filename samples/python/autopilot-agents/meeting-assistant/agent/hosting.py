"""Sample-local HTTP bridge until AgentServer supports the current ClaimsIdentity API."""

from collections.abc import Callable, Mapping
from typing import Any

from azure.ai.agentserver.activity import ActivityAgentServerHost, FoundryStorage, get_hosted_agent_env
from azure.ai.agentserver.core import create_error_response
from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.core import (
    AgentApplication, Authorization, ClaimsIdentity, HttpAdapterBase, MemoryStorage, Storage, TurnState,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class _ActivityRequest:
    def __init__(self, request: Request) -> None:
        self.request = request
        # Digital workers use anonymous outbound connector claims. Incoming
        # platform authentication and AGENTIC user authorization are separate.
        self.claims = ClaimsIdentity(authentication_type="Anonymous")

    @property
    def method(self) -> str:
        return self.request.method

    @property
    def headers(self) -> Mapping[str, str]:
        return self.request.headers

    async def json(self) -> dict[str, Any]:
        activity = self.request.state.activity
        if not isinstance(activity, dict):
            raise ValueError("AgentServer did not supply a parsed Activity object.")
        return activity

    def get_claims_identity(self) -> ClaimsIdentity:
        return self.claims

    def get_path_param(self, name: str) -> str:
        return self.request.path_params.get(name, "")


class MeetingActivityHost(ActivityAgentServerHost):
    """Keep AgentServer infrastructure while owning only its M365 HTTP bridge."""

    def __init__(
        self, *, configure_observability: Callable[..., None] | None,
        storage: Storage | None = None,
    ) -> None:
        super().__init__(
            request_handler=self.handle_activity, digital_worker=True,
            configure_observability=configure_observability,
        )
        self._owned_state_store: FoundryStorage | None = None
        if storage is None:
            if self.config.is_hosted:
                self._owned_state_store = FoundryStorage()
                storage = self._owned_state_store
            else:
                storage = MemoryStorage()
        config = load_configuration_from_env(get_hosted_agent_env(digital_worker=True))
        connections = MsalConnectionManager(**config)
        self._meeting_adapter = HttpAdapterBase(connection_manager=connections)
        self._meeting_application = AgentApplication[TurnState](
            storage=storage, adapter=self._meeting_adapter,
            authorization=Authorization(storage, connections, **config), **config,
        )
        self.shutdown_handler(self.close_storage)

    @property
    def agent_app(self) -> AgentApplication[TurnState]:
        return self._meeting_application

    @property
    def adapter(self) -> HttpAdapterBase:
        return self._meeting_adapter

    async def close_storage(self) -> None:
        storage, self._owned_state_store = self._owned_state_store, None
        if storage is not None:
            await storage.aclose()

    async def handle_activity(self, request: Request) -> Response:
        response = await self.adapter.process_request(_ActivityRequest(request), self.agent_app)
        if response.status_code >= 400:
            message = response.body.get("error") if isinstance(response.body, dict) else None
            return create_error_response(
                "invalid_request" if response.status_code == 400 else "internal_error",
                message or "Request failed",
                status_code=response.status_code, headers=response.headers,
            )
        if response.body is not None:
            return JSONResponse(
                response.body, status_code=response.status_code, headers=response.headers,
            )
        return Response(status_code=response.status_code, headers=response.headers)
