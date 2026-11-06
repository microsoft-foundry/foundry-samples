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
    C# ``builder.AddAgent<A365AgentApplication>``), with forwarded email
    notifications routed through the agent's
    ``handle_agent_notification_activity``.
* The HTTP server endpoints ``/api/messages``, ``/``, ``/liveness``, and
  ``/readiness`` to match the original C# minimal-API routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from os import environ
from typing import Optional

from aiohttp.web import Application, Request, Response, json_response, run_app
from aiohttp.web_middlewares import middleware as web_middleware
from microsoft_agents.activity import (
    Activity,
    ActivityTypes,
    InvokeResponse,
    load_configuration_from_env,
)
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
from microsoft_agents_a365.notifications import EmailResponse
from microsoft_agents_a365.notifications.agent_notification import (
    AgentNotification,
    AgentNotificationActivity,
    ChannelId,
)

from .activity_context import build_activity_context_attachment
from .agent_interface import AgentInterface, check_agent_inheritance
from .capabilities import build_capabilities_attachment
from .email_channel_compat import (
    is_email_activity,
    is_email_notification,
)
from .monitoring_status import (
    build_monitoring_clarification_attachment,
    build_monitoring_configuration_attachment,
    build_monitoring_status_attachment,
)
from .monitoring_config_cards import (
    CONFIGURE_FORM_SUBMIT_TEXT,
    CONFIGURE_FORM_VERB,
    EDIT_JSON_SUBMIT_TEXT,
    EDIT_JSON_VERB,
    build_form_configuration_arguments,
    build_json_configuration_arguments,
    build_monitoring_config_error_attachment,
    build_monitoring_form_attachment,
    build_monitoring_json_attachment,
    get_execute_action,
    get_submit_action,
)
from .token_cache import cache_agentic_token, get_cached_agentic_token


_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

ms_agents_logger = logging.getLogger("microsoft_agents")
ms_agents_logger.addHandler(logging.StreamHandler())
ms_agents_logger.setLevel(logging.INFO)

observability_logger = logging.getLogger("microsoft_agents_a365.observability")
observability_logger.setLevel(logging.ERROR)

logger = logging.getLogger(__name__)
logger.info("📝 Logging configured at level %s (from LOG_LEVEL env)", _LOG_LEVEL_NAME)


def _submitted_json_for_retry(data: dict[str, object]) -> dict[str, object]:
    raw_json = str(data.get("configJson") or "").strip()
    if not raw_json:
        return {}
    try:
        value = json.loads(raw_json)
    except ValueError:
        return {"invalidJson": raw_json}
    return value if isinstance(value, dict) else {"config": value}


# ---------------------------------------------------------------------------
# Key Vault + Application Insights bootstrap (matches Program.cs)
# ---------------------------------------------------------------------------


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
        return
    print(f"AI ConnectionString: {conn}")
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=conn)
    except Exception as ex:
        logger.warning("Failed to configure Application Insights: %s", ex)


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
        self.adapter = CloudAdapter(connection_manager=self.connection_manager)
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

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def _setup_observability_token(
        self, context: TurnContext, tenant_id: str, agent_id: str
    ) -> None:
        if not self.auth_handler_name:
            logger.debug("Skipping observability token exchange (no auth handler)")
            return
        try:
            from microsoft_agents_a365.runtime.environment_utils import (
                get_observability_authentication_scope,
            )

            exaau_token = await self.agent_app.auth.exchange_token(
                context,
                scopes=get_observability_authentication_scope(),
                auth_handler_id=self.auth_handler_name,
            )
            cache_agentic_token(tenant_id, agent_id, exaau_token.token)
            logger.info(
                "✅ Token exchange successful (tenant_id=%s, agent_id=%s)",
                tenant_id,
                agent_id,
            )
        except Exception as ex:
            logger.warning("⚠️ Failed to cache observability token: %s", ex)

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

        await self._setup_observability_token(context, tenant_id, agent_id)
        return tenant_id, agent_id

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _setup_handlers(self) -> None:
        handler_config = (
            {"auth_handlers": [self.auth_handler_name]} if self.auth_handler_name else {}
        )

        async def save_monitoring_configuration(
            context: TurnContext, verb: str, data: dict[str, object]
        ) -> dict[str, object]:
            retry_attachment = (
                build_monitoring_form_attachment()
                if verb == CONFIGURE_FORM_VERB
                else build_monitoring_json_attachment(
                    _submitted_json_for_retry(data)
                )
            )
            try:
                arguments = (
                    build_form_configuration_arguments(data)
                    if verb == CONFIGURE_FORM_VERB
                    else build_json_configuration_arguments(data)
                )
                configuration = await self.agent_instance.configure_mail_monitoring(
                    arguments,
                    self.agent_app.auth,
                    self.auth_handler_name,
                    context,
                )
                error = configuration.get("error")
                if isinstance(error, dict):
                    return build_monitoring_config_error_attachment(
                        str(error.get("message") or "Unable to save configuration."),
                        retry_attachment=retry_attachment,
                    )
                return build_monitoring_configuration_attachment(configuration)
            except ValueError as ex:
                return build_monitoring_config_error_attachment(
                    str(ex), retry_attachment=retry_attachment
                )

        async def help_handler(context: TurnContext, _: TurnState) -> None:
            await context.send_activity(
                Activity(
                    type="message",
                    text="Email Assistant capabilities",
                    attachments=[build_capabilities_attachment()],
                )
            )

        self.agent_app.message("/help", **handler_config)(help_handler)

        async def activity_context_handler(
            context: TurnContext, _: TurnState
        ) -> None:
            session_id = os.getenv("FOUNDRY_AGENT_SESSION_ID", "")
            builder = getattr(
                self.agent_instance,
                "build_activity_context_attachment",
                None,
            )
            if callable(builder):
                attachment = await builder(
                    self.agent_app.auth,
                    self.auth_handler_name,
                    context,
                    session_id,
                )
            else:
                attachment = build_activity_context_attachment(
                    context.activity, session_id
                )
            await context.send_activity(
                Activity(
                    type="message",
                    text="Activity context",
                    attachments=[attachment],
                )
            )

        self.agent_app.message("/activity_context", **handler_config)(
            activity_context_handler
        )

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
                    Activity(
                        type="message",
                        text="Thank you for hiring me. Here is how I can help.",
                        attachments=[build_capabilities_attachment()],
                    )
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
                tenant_id, agent_id = result

                from microsoft_agents_a365.observability.core.middleware.baggage_builder import (
                    BaggageBuilder,
                )

                with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
                    submit_verb, submit_data = get_submit_action(
                        context.activity.value
                    )
                    if submit_verb in {CONFIGURE_FORM_VERB, EDIT_JSON_VERB}:
                        attachment = await save_monitoring_configuration(
                            context, submit_verb, submit_data
                        )
                        await context.send_activity(
                            Activity(
                                type="message",
                                text="Email monitoring configuration result",
                                attachments=[attachment],
                            )
                        )
                        return

                    user_message = context.activity.text or ""
                    if user_message.strip().casefold() in {
                        CONFIGURE_FORM_SUBMIT_TEXT.casefold(),
                        EDIT_JSON_SUBMIT_TEXT.casefold(),
                        "save email monitoring configuration",
                        "save email monitoring json",
                    }:
                        return
                    if user_message.strip().casefold() == "/activity_context":
                        return
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

                    intent = await self.agent_instance.classify_user_intent(
                        user_message
                    )
                    if intent == self.agent_instance.CAPABILITIES_INTENT:
                        await context.send_activity(
                            Activity(
                                type="message",
                                text="Email Assistant capabilities",
                                attachments=[build_capabilities_attachment()],
                            )
                        )
                        return

                    if intent == self.agent_instance.MONITORING_STATUS_INTENT:
                        status = await self.agent_instance.get_mail_monitoring_status(
                            self.agent_app.auth,
                            self.auth_handler_name,
                            context,
                        )
                        await context.send_activity(
                            Activity(
                                type="message",
                                text="Email monitoring status",
                                attachments=[
                                    build_monitoring_status_attachment(status)
                                ],
                            )
                        )
                        return

                    if intent in {
                        self.agent_instance.CONFIGURE_MONITORING_FORM_INTENT,
                        self.agent_instance.EDIT_MONITORING_JSON_INTENT,
                    }:
                        status = await self.agent_instance.get_mail_monitoring_status(
                            self.agent_app.auth,
                            self.auth_handler_name,
                            context,
                        )
                        if isinstance(status.get("error"), dict):
                            await context.send_activity(
                                Activity(
                                    type="message",
                                    text="Email monitoring configuration unavailable",
                                    attachments=[
                                        build_monitoring_status_attachment(status)
                                    ],
                                )
                            )
                            return
                        config = status.get("config") if isinstance(status, dict) else None
                        if intent == self.agent_instance.EDIT_MONITORING_JSON_INTENT:
                            attachment = build_monitoring_json_attachment(config)
                            text = "Edit email monitoring JSON"
                        else:
                            attachment = build_monitoring_form_attachment(config)
                            text = "Configure email monitoring"
                        await context.send_activity(
                            Activity(type="message", text=text, attachments=[attachment])
                        )
                        return

                    if intent == self.agent_instance.ENABLE_MONITORING_INTENT:
                        result = await self.agent_instance.enable_mail_monitoring(
                            self.agent_app.auth,
                            self.auth_handler_name,
                            context,
                        )
                        if result.get("enabled") is True:
                            attachment = build_monitoring_configuration_attachment(result)
                            text = "Email monitoring enabled"
                        else:
                            attachment = build_monitoring_clarification_attachment(
                                str(result.get("message") or "Provide a monitoring rule.")
                            )
                            text = "Complete your monitoring rule"
                        await context.send_activity(
                            Activity(type="message", text=text, attachments=[attachment])
                        )
                        return

                    # Multi-message pattern: immediate ack, typing indicator loop,
                    # then the final LLM response. Mirrors the C# StreamingResponse
                    # flow (QueueInformativeUpdateAsync + QueueTextChunk).
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
                        if response and intent == (
                            self.agent_instance.CONFIGURE_MONITORING_INTENT
                        ):
                            await context.send_activity(
                                Activity(
                                    type="message",
                                    text="Complete your monitoring rule",
                                    attachments=[
                                        build_monitoring_clarification_attachment(
                                            response
                                        )
                                    ],
                                )
                            )
                        elif response:
                            await context.send_activity(response)
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

        async def on_adaptive_card_action(
            context: TurnContext, _: TurnState
        ) -> InvokeResponse:
            result = await self._validate_agent_and_setup_context(context)
            if result is None:
                return InvokeResponse(status=503, body={"statusCode": 503})

            verb, data = get_execute_action(context.activity.value)
            if verb not in {CONFIGURE_FORM_VERB, EDIT_JSON_VERB}:
                return InvokeResponse(
                    status=400,
                    body={
                        "statusCode": 400,
                        "type": "application/vnd.microsoft.error",
                        "value": {"message": "Unsupported Adaptive Card action."},
                    },
                )

            attachment = await save_monitoring_configuration(context, verb, data)

            return InvokeResponse(
                status=200,
                body={
                    "statusCode": 200,
                    "type": "application/vnd.microsoft.card.adaptive",
                    "value": attachment["content"],
                },
            )

        self.agent_app.add_route(
            lambda context: (
                context.activity.type == ActivityTypes.invoke
                and context.activity.name == "adaptiveCard/action"
            ),
            on_adaptive_card_action,
            is_invoke=True,
            **handler_config,
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
                tenant_id, agent_id = result

                from microsoft_agents_a365.observability.core.middleware.baggage_builder import (
                    BaggageBuilder,
                )

                with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
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
                        if not response:
                            return
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

        logger.warning("⚠️ No client credential auth env vars; running anonymous")
        return None

    # ------------------------------------------------------------------
    # HTTP server
    # ------------------------------------------------------------------

    def start_server(
        self, auth_configuration: AgentAuthConfiguration | None = None
    ) -> None:
        async def entry_point(req: Request) -> Response:
            try:
                body_bytes = await req.read()
                try:
                    body_repr = body_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    body_repr = repr(body_bytes)
                logger.info(
                    "📥 /api/messages request | method=%s | content-type=%s | size=%d bytes | body=%s",
                    req.method,
                    req.headers.get("Content-Type", ""),
                    len(body_bytes),
                    body_repr,
                )
            except Exception as ex:
                logger.warning("Failed to log incoming request body: %s", ex)

            return await start_agent_process(
                req, req.app["agent_app"], req.app["adapter"]
            )

        async def root(_req: Request) -> Response:
            return Response(text="Foundry M365 Autopilot is running.")

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

        # Foundry forwards Activity-protocol traffic to /activity/messages,
        # while the Bot Framework emulator uses /api/messages locally.
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

        port = int(environ.get("PORT", 8088))
        host_addr = environ.get("HOST", "0.0.0.0")

        print("=" * 80)
        print(f"🏢 {self.agent_class.__name__}")
        print("=" * 80)
        print(f"🔒 Auth: {'Enabled' if auth_configuration else 'Anonymous'}")
        print(f"🚀 Server: {host_addr}:{port}")
        print(f"📚 Endpoint: http://{host_addr}:{port}/api/messages")
        print(f"❤️  Health: http://{host_addr}:{port}/api/health\n")

        try:
            run_app(app, host=host_addr, port=port, handle_signals=True)
        except KeyboardInterrupt:
            print("\n👋 Server stopped")
