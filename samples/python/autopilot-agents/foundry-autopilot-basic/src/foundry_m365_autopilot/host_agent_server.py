"""Activity Protocol host for the Basic Digital Worker sample."""

from __future__ import annotations

import asyncio
import logging
import os
from os import environ
from typing import Optional

from aiohttp.web import Application, Request, Response, json_response, run_app
from aiohttp.web_middlewares import middleware as web_middleware
from microsoft_agents.activity import Activity, load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import (
    AgentApplication,
    AgentAuthConfiguration,
    AuthenticationConstants,
    Authorization,
    ClaimsIdentity,
    MemoryStorage,
    TurnContext,
    TurnState,
)

from .agent_interface import AgentInterface, check_agent_inheritance
from .activity_context import build_activity_context_attachment
from .capabilities import build_capabilities_attachment
from .token_cache import cache_agentic_token, get_cached_agentic_token

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _configure_key_vault() -> None:
    key_vault_name = os.getenv("KeyVaultName") or os.getenv("KEY_VAULT_NAME")
    if not key_vault_name:
        return
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(
            vault_url=f"https://{key_vault_name}.vault.azure.net/",
            credential=DefaultAzureCredential(),
        )
        for properties in client.list_properties_of_secrets():
            secret = client.get_secret(properties.name)
            os.environ.setdefault(
                properties.name.replace("--", "__"), secret.value or ""
            )
    except Exception as ex:
        logger.warning("Failed to load Key Vault settings: %s", ex)


def _configure_application_insights() -> None:
    connection_string = os.getenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    ) or os.getenv("ApplicationInsights__ConnectionString")
    if not connection_string:
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
    except Exception as ex:
        logger.warning("Failed to configure Application Insights: %s", ex)


def _configure_blueprint_client_id() -> None:
    blueprint_client_id = os.getenv("FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID")
    if blueprint_client_id:
        os.environ[
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
        ] = blueprint_client_id


_configure_key_vault()
_configure_application_insights()
_configure_blueprint_client_id()
agents_sdk_config = load_configuration_from_env(environ)


def create_and_run_host(
    agent_class: type[AgentInterface], *agent_args, **agent_kwargs
) -> None:
    if not check_agent_inheritance(agent_class):
        raise TypeError(
            f"Agent class {agent_class.__name__} must inherit from AgentInterface"
        )

    try:
        from microsoft.opentelemetry import use_microsoft_opentelemetry

        use_microsoft_opentelemetry(
            enable_a365=True,
            enable_azure_monitor=False,
            a365_token_resolver=lambda agent_id, tenant_id: (
                get_cached_agentic_token(tenant_id, agent_id) or ""
            ),
        )
    except Exception as ex:
        logger.warning("Microsoft OpenTelemetry distro not initialized: %s", ex)

    host = GenericAgentHost(agent_class, *agent_args, **agent_kwargs)
    host.start_server(host.create_auth_configuration())


class GenericAgentHost:
    def __init__(
        self,
        agent_class: type[AgentInterface],
        *agent_args,
        **agent_kwargs,
    ) -> None:
        self.auth_handler_name = os.getenv("AUTH_HANDLER_NAME", "AGENTIC") or None
        self.agent_class = agent_class
        self.agent_args = agent_args
        self.agent_kwargs = agent_kwargs
        self.agent_instance: Optional[AgentInterface] = None

        self.storage = MemoryStorage()
        self.connection_manager = MsalConnectionManager(**agents_sdk_config)
        self.adapter = CloudAdapter(connection_manager=self.connection_manager)
        self.authorization = Authorization(
            self.storage, self.connection_manager, **agents_sdk_config
        )
        self.agent_app = AgentApplication[TurnState](
            storage=self.storage,
            adapter=self.adapter,
            authorization=self.authorization,
            **agents_sdk_config,
        )
        self._setup_handlers()

    async def _setup_observability_token(
        self, context: TurnContext, tenant_id: str, agent_id: str
    ) -> None:
        if not self.auth_handler_name:
            return
        try:
            from microsoft_agents_a365.runtime.environment_utils import (
                get_observability_authentication_scope,
            )

            exchanged = await self.agent_app.auth.exchange_token(
                context,
                scopes=get_observability_authentication_scope(),
                auth_handler_id=self.auth_handler_name,
            )
            cache_agentic_token(tenant_id, agent_id, exchanged.token)
        except Exception as ex:
            logger.warning("Failed to cache observability token: %s", ex)

    async def _validate_agent_and_setup_context(
        self, context: TurnContext
    ) -> tuple[str, str] | None:
        if not self.agent_instance:
            await context.send_activity("Sorry, the agent is not available.")
            return None
        recipient = context.activity.recipient
        tenant_id = getattr(recipient, "tenant_id", "") or ""
        agent_id = getattr(recipient, "agentic_app_id", "") or ""
        await self._setup_observability_token(context, tenant_id, agent_id)
        return tenant_id, agent_id

    def _setup_handlers(self) -> None:
        handler_config = (
            {"auth_handlers": [self.auth_handler_name]}
            if self.auth_handler_name
            else {}
        )

        async def help_handler(context: TurnContext, _: TurnState) -> None:
            await context.send_activity(
                Activity(
                    type="message",
                    text="How I can help",
                    attachments=[build_capabilities_attachment()],
                )
            )

        self.agent_app.conversation_update("membersAdded", **handler_config)(
            help_handler
        )
        self.agent_app.message("/help", **handler_config)(help_handler)

        async def activity_context_handler(
            context: TurnContext, _: TurnState
        ) -> None:
            session_id = os.getenv("FOUNDRY_AGENT_SESSION_ID", "")
            await context.send_activity(
                Activity(
                    type="message",
                    text="Activity context",
                    attachments=[
                        build_activity_context_attachment(
                            context.activity, session_id=session_id
                        )
                    ],
                )
            )

        self.agent_app.message("/activity_context", **handler_config)(
            activity_context_handler
        )

        @self.agent_app.activity("installationUpdate")
        async def on_installation_update(
            context: TurnContext, _: TurnState
        ) -> None:
            if getattr(context.activity, "action", None) == "add":
                await context.send_activity(
                    "Thank you for hiring me. How can I help?"
                )

        @self.agent_app.activity("message", **handler_config)
        async def on_message(context: TurnContext, _: TurnState) -> None:
            result = await self._validate_agent_and_setup_context(context)
            if result is None:
                return
            tenant_id, agent_id = result
            user_message = context.activity.text or ""
            if user_message.strip().casefold() == "/activity_context":
                return
            if not user_message.strip() or user_message.strip() == "/help":
                return

            intent = await self.agent_instance.classify_user_intent(user_message)
            if intent == "CAPABILITIES":
                await context.send_activity(
                    Activity(
                        type="message",
                        text="How I can help",
                        attachments=[build_capabilities_attachment()],
                    )
                )
                return

            from microsoft_agents_a365.observability.core.middleware.baggage_builder import (
                BaggageBuilder,
            )

            with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
                await context.send_activity("Working on your request...")
                await context.send_activity(Activity(type="typing"))

                async def typing_loop() -> None:
                    try:
                        while True:
                            await asyncio.sleep(4)
                            await context.send_activity(Activity(type="typing"))
                    except asyncio.CancelledError:
                        pass

                typing_task = asyncio.create_task(typing_loop())
                try:
                    response = await self.agent_instance.process_user_message(
                        user_message,
                        self.agent_app.auth,
                        self.auth_handler_name,
                        context,
                    )
                    await context.send_activity(response)
                finally:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

    async def initialize_agent(self) -> None:
        if self.agent_instance is None:
            self.agent_instance = self.agent_class(
                *self.agent_args, **self.agent_kwargs
            )
            await self.agent_instance.initialize()

    async def cleanup(self) -> None:
        if self.agent_instance:
            await self.agent_instance.cleanup()

    def create_auth_configuration(self) -> AgentAuthConfiguration | None:
        client_id = environ.get("CLIENT_ID") or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
        )
        tenant_id = environ.get("TENANT_ID") or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID"
        )
        client_secret = environ.get("CLIENT_SECRET") or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET"
        )
        if client_id and tenant_id and client_secret:
            return AgentAuthConfiguration(
                client_id=client_id,
                tenant_id=tenant_id,
                client_secret=client_secret,
                scopes=["5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default"],
            )
        return None

    def start_server(
        self, auth_configuration: AgentAuthConfiguration | None = None
    ) -> None:
        async def entry_point(req: Request) -> Response:
            return await start_agent_process(
                req, req.app["agent_app"], req.app["adapter"]
            )

        async def root(_req: Request) -> Response:
            return Response(text="Foundry Autopilot Basic is running.")

        async def health(_req: Request) -> Response:
            return json_response(
                {
                    "status": "ok",
                    "agent_type": self.agent_class.__name__,
                    "agent_initialized": self.agent_instance is not None,
                }
            )

        middlewares = []
        if auth_configuration:

            @web_middleware
            async def jwt_with_health_bypass(request, handler):
                if request.path in {"/", "/liveness", "/readiness", "/api/health"}:
                    return await handler(request)
                return await jwt_authorization_middleware(request, handler)

            middlewares.append(jwt_with_health_bypass)

        @web_middleware
        async def anonymous_claims(request, handler):
            if not auth_configuration:
                request["claims_identity"] = ClaimsIdentity(
                    {
                        AuthenticationConstants.AUDIENCE_CLAIM: "anonymous",
                        AuthenticationConstants.APP_ID_CLAIM: "anonymous-app",
                    },
                    False,
                    "Anonymous",
                )
            return await handler(request)

        middlewares.append(anonymous_claims)
        app = Application(middlewares=middlewares)
        app.router.add_post("/api/messages", entry_point)
        app.router.add_get("/api/messages", lambda _: Response(status=200))
        app.router.add_post("/activity/messages", entry_point)
        app.router.add_get("/activity/messages", lambda _: Response(status=200))
        app.router.add_get("/", root)
        app.router.add_get("/liveness", root)
        app.router.add_get("/readiness", root)
        app.router.add_get("/api/health", health)
        app["agent_configuration"] = auth_configuration
        app["agent_app"] = self.agent_app
        app["adapter"] = self.agent_app.adapter
        app.on_startup.append(lambda app: self.initialize_agent())
        app.on_shutdown.append(lambda app: self.cleanup())
        run_app(
            app,
            host=environ.get("HOST", "0.0.0.0"),
            port=int(environ.get("PORT", 8088)),
            handle_signals=True,
        )
