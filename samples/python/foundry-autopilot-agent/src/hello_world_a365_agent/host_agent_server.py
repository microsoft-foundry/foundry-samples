# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Generic Agent Host Server — hosts agents implementing :class:`AgentInterface`.

Python port of the C# ``Program.cs`` + ``A365AgentApplication``. Wires up:

* Azure Key Vault as a configuration source when ``KEY_VAULT_NAME`` is set.
* Application Insights telemetry when
  ``APPLICATIONINSIGHTS_CONNECTION_STRING`` (or the legacy
  ``ApplicationInsights__ConnectionString`` binding from ``appsettings.json``)
  is set.
* The Microsoft Agents SDK ``AgentApplication`` (the Python equivalent of the
  C# ``builder.AddAgent<A365AgentApplication>``), with all four agentic
  notification handlers (Email, Word, Excel, PowerPoint) routed through the
  agent's ``handle_agent_notification_activity``.
* The HTTP server endpoints ``/activity/messages``, ``/``, ``/liveness``, and
  ``/readiness`` to match the original C# minimal-API routes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
from os import environ
from typing import Optional

from aiohttp.web import Application, Request, Response, json_response, run_app
from aiohttp.web_middlewares import middleware as web_middleware
from microsoft_agents.activity import (
    Activity,
    ClientCitation,
    ClientCitationAppearance,
    load_configuration_from_env,
)
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import (
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
from microsoft_agents_a365.notifications import EmailResponse
from microsoft_agents_a365.notifications.agent_notification import (
    AgentNotification,
    AgentNotificationActivity,
    ChannelId,
)
from opentelemetry import propagate, trace
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

from .agent_interface import AgentInterface, check_agent_inheritance
from .email_channel_compat import (
    is_email_activity,
    is_email_notification,
    is_wpx_comment_activity,
)
from .request_correlation import (
    AgentRequestCorrelationMiddleware,
    CorrelatingCloudAdapter,
)

_CITATION_REFERENCE_PATTERN = re.compile(
    r'^\[(\d+)\]:\s+(https?://\S+?)(?:\s+"([^"]*)")?\s*$',
    re.MULTILINE,
)


def _create_message_activity(text: str) -> Activity:
    activity = Activity(type="message", text=text, text_format="markdown")
    citations = [
        ClientCitation(
            position=int(match.group(1)),
            appearance=ClientCitationAppearance(
                name=(match.group(3) or match.group(2))[:80],
                url=match.group(2),
            ),
        )
        for match in _CITATION_REFERENCE_PATTERN.finditer(text)
    ]
    if citations:
        activity.add_ai_metadata(citations=citations)
    return activity


def is_wpx_comment_notification(notification_activity: AgentNotificationActivity) -> bool:
    """Check if notification is a Word/Excel/PowerPoint comment notification."""
    try:
        from microsoft_agents_a365.notifications import NotificationTypes
        notification_type = getattr(notification_activity, "notification_type", None)
        if notification_type == NotificationTypes.WPX_COMMENT:
            return True
    except (ImportError, AttributeError):
        pass
    
    notification_type = getattr(notification_activity, "notification_type", None)
    value = getattr(notification_type, "value", notification_type)
    normalized = str(value or "").lower()
    return "comment" in normalized and (
        "wpx" in normalized
        or "word" in normalized
        or "excel" in normalized
        or "powerpoint" in normalized
    )


_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

ms_agents_logger = logging.getLogger("microsoft_agents")
ms_agents_logger.addHandler(logging.StreamHandler())
ms_agents_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.info("📝 Logging configured at level %s (from LOG_LEVEL env)", _LOG_LEVEL_NAME)


# ---------------------------------------------------------------------------
# Key Vault + Application Insights bootstrap (matches Program.cs)
# ---------------------------------------------------------------------------


class _FoundryProjectIdSpanProcessor(SpanProcessor):
    def __init__(self, project_resource_id: str) -> None:
        self._project_resource_id = project_resource_id

    def on_start(self, span, parent_context=None) -> None:
        span.set_attribute(
            "microsoft.foundry.project.id",
            self._project_resource_id,
        )


def _configure_key_vault() -> None:
    key_vault_name = os.getenv("KeyVaultName") or os.getenv("KEY_VAULT_NAME")
    if not key_vault_name:
        print("KeyVaultName not configured. Key Vault integration skipped.")
        return

    key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=key_vault_uri, credential=DefaultAzureCredential())
        for secret_properties in client.list_properties_of_secrets():
            name = secret_properties.name
            secret = client.get_secret(name)
            env_name = name.replace("--", "__")
            os.environ.setdefault(env_name, secret.value or "")
        print(f"Azure Key Vault configured: {key_vault_uri}")
    except Exception as ex:
        logger.warning("Failed to load secrets from %s: %s", key_vault_uri, ex)


def _configure_application_insights() -> None:
    conn = (
        os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        or os.getenv("ApplicationInsights__ConnectionString")
    )
    if not conn:
        logger.warning(
            "Application Insights is not configured. "
            "Set APPLICATIONINSIGHTS_CONNECTION_STRING to enable telemetry."
        )
        return

    try:
        from azure.ai.projects.telemetry import AIProjectInstrumentor
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true"
        )
        project_resource_id = os.getenv("FOUNDRY_PROJECT_ARM_ID")
        if not project_resource_id:
            logger.warning(
                "FOUNDRY_PROJECT_ARM_ID is not set; spans will not include "
                "microsoft.foundry.project.id."
            )
        span_processors = (
            [_FoundryProjectIdSpanProcessor(project_resource_id)]
            if project_resource_id
            else []
        )
        configure_azure_monitor(
            connection_string=conn,
            sampling_ratio=1.0,
            span_processors=span_processors,
        )
        AIProjectInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        logger.info("Application Insights and Foundry GenAI telemetry configured.")
    except Exception:
        logger.exception("Failed to configure Application Insights telemetry.")


def _configure_blueprint_client_id() -> None:
    blueprint_client_id = os.getenv("FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID")
    if blueprint_client_id:
        os.environ[
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
        ] = blueprint_client_id
        print(
            "ServiceConnection ClientId set from "
            "FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID."
        )
    else:
        print(
            "FOUNDRY_AGENT_BLUEPRINT_CLIENT_ID not set. "
            "ServiceConnection ClientId not configured."
        )


_configure_key_vault()
_configure_application_insights()
_configure_blueprint_client_id()


agents_sdk_config = load_configuration_from_env(environ)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_and_run_host(agent_class: type[AgentInterface], *agent_args, **agent_kwargs) -> None:
    """Create and run a generic agent host."""

    if not check_agent_inheritance(agent_class):
        raise TypeError(
            f"Agent class {agent_class.__name__} must inherit from AgentInterface"
        )

    host = GenericAgentHost(agent_class, *agent_args, **agent_kwargs)
    auth_config = host.create_auth_configuration()
    host.start_server(auth_config)


# ---------------------------------------------------------------------------
# GenericAgentHost
# ---------------------------------------------------------------------------


class GenericAgentHost:
    """Generic host for agents implementing :class:`AgentInterface`."""

    def __init__(
        self,
        agent_class: type[AgentInterface],
        *agent_args,
        **agent_kwargs,
    ) -> None:
        if not check_agent_inheritance(agent_class):
            raise TypeError(
                f"Agent class {agent_class.__name__} must inherit from AgentInterface"
            )

        # The handler key inside AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS
        # comes through verbatim from the env-var split. Set AUTH_HANDLER_NAME
        # to match (uppercase) — empty disables agentic auth entirely.
        self.auth_handler_name = os.getenv("AUTH_HANDLER_NAME", "AGENTIC") or None
        if self.auth_handler_name:
            logger.info("🔐 Using auth handler: %s", self.auth_handler_name)
        else:
            logger.info("🔓 No auth handler configured (AUTH_HANDLER_NAME not set)")

        self.agent_class = agent_class
        self.agent_args = agent_args
        self.agent_kwargs = agent_kwargs
        self.agent_instance: Optional[AgentInterface] = None

        self.storage = MemoryStorage()
        self.connection_manager = MsalConnectionManager(**agents_sdk_config)
        self.adapter = CorrelatingCloudAdapter(
            connection_manager=self.connection_manager
        )
        self.adapter.use(AgentRequestCorrelationMiddleware())
        self.authorization = Authorization(
            self.storage, self.connection_manager, **agents_sdk_config
        )

        # Diagnostic: dump what the SDK actually loaded from env so we can tell
        # whether AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__<name>__... env
        # vars reached the container and were parsed as expected.
        _agent_app_cfg = agents_sdk_config.get("AGENTAPPLICATION", {})
        _user_auth_cfg = _agent_app_cfg.get("USERAUTHORIZATION", {})
        _handlers_cfg = _user_auth_cfg.get("HANDLERS", {})
        logger.info(
            "🔎 Auth handlers loaded from config: env_keys=%s | "
            "registered=%s | default=%s",
            list(_handlers_cfg.keys()),
            list(self.authorization._handlers.keys()),
            getattr(self.authorization, "_default_handler_id", None),
        )
        if self.auth_handler_name and self.auth_handler_name not in self.authorization._handlers:
            logger.error(
                "❌ AUTH_HANDLER_NAME=%s is NOT in registered handlers %s. "
                "Check that AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__%s__SETTINGS__TYPE "
                "is set in the container env.",
                self.auth_handler_name,
                list(self.authorization._handlers.keys()),
                self.auth_handler_name,
            )

        self.agent_app = AgentApplication[TurnState](
            storage=self.storage,
            adapter=self.adapter,
            authorization=self.authorization,
            **agents_sdk_config,
        )
        self.agent_notification = AgentNotification(self.agent_app)
        self._setup_handlers()
        logger.info("✅ Notification handlers registered successfully")

    async def _validate_agent_and_setup_context(self, context: TurnContext):
        recipient = context.activity.recipient
        tenant_id = getattr(recipient, "tenant_id", "") or ""
        agent_id = getattr(recipient, "agentic_app_id", "") or ""
        logger.info("🔍 tenant_id=%s, agent_id=%s", tenant_id, agent_id)

        if not self.agent_instance:
            logger.error("Agent not available")
            if not is_email_activity(context.activity):
                await context.send_activity("❌ Sorry, the agent is not available.")
            return None

        return tenant_id, agent_id

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _setup_handlers(self) -> None:
        handler_config = (
            {"auth_handlers": [self.auth_handler_name]} if self.auth_handler_name else {}
        )

        async def help_handler(context: TurnContext, _: TurnState) -> None:
            await context.send_activity(
                f"👋 **Hi there!** I'm **{self.agent_class.__name__}**, your AI assistant.\n\n"
                "How can I help you today?"
            )

        self.agent_app.conversation_update("membersAdded", **handler_config)(help_handler)
        self.agent_app.message("/help", **handler_config)(help_handler)

        @self.agent_app.activity("installationUpdate")
        async def on_installation_update(context: TurnContext, _: TurnState) -> None:
            action = getattr(context.activity, "action", None)
            from_prop = context.activity.from_property
            logger.info(
                "InstallationUpdate received — Action: '%s', DisplayName: '%s', UserId: '%s'",
                action or "(none)",
                getattr(from_prop, "name", "(unknown)") if from_prop else "(unknown)",
                getattr(from_prop, "id", "(unknown)") if from_prop else "(unknown)",
            )
            if action == "add":
                await context.send_activity(
                    "Thank you for hiring me! Looking forward to assisting you in "
                    "your professional journey!"
                )
            elif action == "remove":
                await context.send_activity(
                    "Thank you for your time, I enjoyed working with you."
                )

        @self.agent_app.activity("message", **handler_config)
        async def on_message(context: TurnContext, _: TurnState) -> None:
            try:
                result = await self._validate_agent_and_setup_context(context)
                if result is None:
                    return

                user_message = context.activity.text or ""
                if not user_message.strip() or user_message.strip() == "/help":
                    return

                logger.info("📨 %s", user_message)

                if is_email_activity(context.activity):
                    await self.agent_instance.process_user_message(
                        user_message,
                        self.agent_app.auth,
                        self.auth_handler_name,
                        context,
                    )
                    return

                # Multi-message pattern: immediate ack, typing indicator loop,
                # then the final LLM response. Mirrors the C# StreamingResponse
                # flow (QueueInformativeUpdateAsync + QueueTextChunk).
                if not is_wpx_comment_activity(context.activity):
                    await context.send_activity("Working on your request...")
                await context.send_activity(Activity(type="typing"))

                async def _typing_loop() -> None:
                    try:
                        while True:
                            await asyncio.sleep(4)
                            await context.send_activity(Activity(type="typing"))
                    except asyncio.CancelledError:
                        pass

                typing_task = asyncio.create_task(_typing_loop())
                try:
                    response = await self.agent_instance.process_user_message(
                        user_message,
                        self.agent_app.auth,
                        self.auth_handler_name,
                        context,
                    )
                    await context.send_activity(_create_message_activity(response))
                finally:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

            except Exception as ex:
                logger.exception("Error processing message")
                if is_email_activity(context.activity):
                    return
                session_id = os.getenv("FOUNDRY_AGENT_SESSION_ID") or "(not set)"
                await context.send_activity(
                    "Sorry, something went wrong while processing your message.\n"
                    f"FOUNDRY_AGENT_SESSION_ID: {session_id}\n"
                    f"Exception: {ex}"
                )

        @self.agent_notification.on_agent_notification(
            channel_id=ChannelId(channel="agents", sub_channel="*"),
            **handler_config,
        )
        async def on_notification(
            context: TurnContext,
            state: TurnState,
            notification_activity: AgentNotificationActivity,
        ) -> None:
            try:
                result = await self._validate_agent_and_setup_context(context)
                if result is None:
                    return

                logger.info("📬 %s", notification_activity.notification_type)

                if not hasattr(
                    self.agent_instance, "handle_agent_notification_activity"
                ):
                    logger.warning("⚠️ Agent doesn't support notifications")
                    await context.send_activity(
                        "This agent doesn't support notification handling yet."
                    )
                    return

                is_email = is_email_notification(notification_activity)

                response = await self.agent_instance.handle_agent_notification_activity(
                    notification_activity,
                    self.agent_app.auth,
                    self.auth_handler_name,
                    context,
                )

                if is_email:
                    response_activity = EmailResponse.create_email_response_activity(
                        response
                    )
                    await context.send_activity(response_activity)
                    return

                if not response:
                    return

                await context.send_activity(response)
            except Exception as ex:
                logger.exception("Notification error")
                await context.send_activity(
                    f"Sorry, I encountered an error processing the notification: {ex}"
                )

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize_agent(self) -> None:
        if self.agent_instance is None:
            logger.info("🤖 Initializing %s...", self.agent_class.__name__)
            self.agent_instance = self.agent_class(*self.agent_args, **self.agent_kwargs)
            await self.agent_instance.initialize()

    async def cleanup(self) -> None:
        if self.agent_instance:
            try:
                await self.agent_instance.cleanup()
            except Exception:
                logger.exception("Cleanup error")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

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
            logger.info("🔒 Using Client Credentials authentication")
            return AgentAuthConfiguration(
                client_id=client_id,
                tenant_id=tenant_id,
                client_secret=client_secret,
                scopes=["5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default"],
            )

        logger.warning("⚠️ No auth env vars; running anonymous")
        return None

    # ------------------------------------------------------------------
    # HTTP server
    # ------------------------------------------------------------------

    def start_server(
        self, auth_configuration: AgentAuthConfiguration | None = None
    ) -> None:
        async def entry_point(req: Request) -> Response:
            tracer = trace.get_tracer(__name__)
            parent_context = propagate.extract(req.headers)

            with tracer.start_as_current_span(
                "POST /activity/messages",
                context=parent_context,
                kind=SpanKind.SERVER,
                attributes={
                    "http.request.method": req.method,
                    "http.route": "/activity/messages",
                    "url.scheme": req.scheme,
                    "server.address": req.host,
                },
            ) as request_span:
                try:
                    body_bytes = await req.read()
                    try:
                        body_repr = body_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        body_repr = repr(body_bytes)
                    logger.info(
                        "📥 /activity/messages request | method=%s | content-type=%s | size=%d bytes | body=%s",
                        req.method,
                        req.headers.get("Content-Type", ""),
                        len(body_bytes),
                        body_repr,
                    )
                except Exception as ex:
                    logger.warning("Failed to log incoming request body: %s", ex)

                try:
                    response = await start_agent_process(
                        req, req.app["agent_app"], req.app["adapter"]
                    )
                except Exception as ex:
                    request_span.set_status(Status(StatusCode.ERROR, str(ex)))
                    raise

                status_code = response.status if response is not None else 202
                request_span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    request_span.set_status(Status(StatusCode.ERROR))
                return response

        async def root(_req: Request) -> Response:
            return Response(text="Hello World from HelloWorldA365Agent!")

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
                # Skip JWT validation for health/liveness/readiness/root endpoints
                # so that container orchestrators can reach them without a bearer token.
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

        desired_port = int(environ.get("PORT", 8088))
        port = desired_port
        host_addr = environ.get("HOST", "0.0.0.0")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", desired_port)) == 0:
                port = desired_port + 1

        print("=" * 80)
        print(f"🏢 {self.agent_class.__name__}")
        print("=" * 80)
        print(f"🔒 Auth: {'Enabled' if auth_configuration else 'Anonymous'}")
        print(f"🚀 Server: {host_addr}:{port}")
        print(f"📚 Endpoint: http://{host_addr}:{port}/activity/messages")
        print(f"❤️  Health: http://{host_addr}:{port}/api/health\n")

        try:
            run_app(app, host=host_addr, port=port, handle_signals=True)
        except KeyboardInterrupt:
            print("\n👋 Server stopped")
