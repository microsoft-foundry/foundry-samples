"""Thin GitHub Copilot SDK harness for the resilient hosted agent.

This module isolates every direct dependency on the ``github-copilot-sdk`` so
``agent.py`` (the resilient task) and ``main.py`` (the HTTP surface) stay small
and SDK-version-agnostic. It owns:

* **Auth + backend selection** — BYOK Foundry model (Managed Identity bearer
  token via ``DefaultAzureCredential``) or the GitHub Copilot model
  (``GITHUB_TOKEN``). Foundry takes precedence when both are set.
* **Session lifecycle** — ``create_session`` (fresh) vs ``resume_session``
  (crash recovery). The Copilot CLI persists each session's workspace to disk,
  so ``resume_session`` rehydrates the conversation on a restarted container.
* **Event pump** — every ``SessionEvent`` the CLI emits is pushed onto an
  ``asyncio.Queue`` and re-exposed as an async iterator the task drains and
  forwards to the SSE stream.
* **Elicitation (human-in-the-loop) bridge** — the SDK's
  ``on_elicitation_request`` callback parks an ``asyncio.Future`` and notifies
  the task layer (which emits a client-visible request and persists a durable
  marker). The client's answer resolves the Future so the callback returns an
  ``ElicitationResult`` and the model continues.

The sample pins the Copilot SDK version in ``requirements.txt`` so the imports
and callback contracts remain reproducible.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from copilot import CopilotClient, PermissionHandler, ProviderConfig
from copilot.session_events import SessionEventType

logger = logging.getLogger(__name__)

# Callback the task registers so an elicitation request (raised by the model
# mid-turn) is surfaced to the client and persisted durably. Receives
# (elicitation_id, message, requested_schema).
ElicitRequestCallback = Callable[[str, str, dict], Awaitable[None]]

# Sentinel end-of-stream marker pushed onto the queue when the agent goes idle.
_IDLE = object()


class CopilotHarness:
    """Owns one Copilot CLI client + session and bridges it to the task."""

    def __init__(self) -> None:
        self._client: CopilotClient | None = None
        self.session: Any = None
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._unsubscribe: Callable[[], None] | None = None
        # elicitation_id -> Future[ElicitationResult]
        self._pending_elicitations: dict[str, asyncio.Future] = {}
        self._on_elicit_request: ElicitRequestCallback | None = None

    # -- backend selection ---------------------------------------------------

    @staticmethod
    def _byok_provider() -> tuple[Any | None, str | None]:
        """Return (ProviderConfig, model) for BYOK mode, else (None, None).

        Mints a Managed-Identity bearer token for the Foundry project endpoint.
        NOTE: the token is minted once at session creation; for a genuinely
        multi-hour run you would refresh it (out of scope for this sample).
        """
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
        if not endpoint or not model:
            return None, None

        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        token = (
            DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
        )
        provider = ProviderConfig(
            type="azure",
            base_url=endpoint,
            wire_api="responses",
            bearer_token=token,
        )
        return provider, model

    @staticmethod
    def has_backend() -> bool:
        """True if either a BYOK Foundry model or a GITHUB_TOKEN is configured."""
        byok = bool(
            os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
            and os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        )
        return byok or bool(os.environ.get("GITHUB_TOKEN"))

    # -- lifecycle -----------------------------------------------------------

    async def start(
        self,
        session_id: str,
        *,
        recover: bool,
        on_elicit_request: ElicitRequestCallback | None = None,
        working_directory: str | None = None,
        config_directory: str | None = None,
    ) -> None:
        """Create (fresh) or resume (recovery) the Copilot session.

        :param recover: When True, ``resume_session`` rehydrates the session
            from ``config_dir`` after a crash; when False, a new session is
            created. Resume falls back to create if no persisted session exists.
        :param config_directory: The Copilot CLI configuration directory where the
            session (its SQLite ``session-store.db`` + ``session-state/`` tree)
            is persisted. Point this at a per-session, durable-store-backed path
            so ``resume_session`` can rehydrate after a container restart.
        """
        self._on_elicit_request = on_elicit_request

        provider, model = self._byok_provider()
        github_token = os.environ.get("GITHUB_TOKEN")
        if provider:
            self._client = CopilotClient()  # BYOK — no token needed
        elif github_token:
            self._client = CopilotClient(github_token=github_token)
        else:
            raise RuntimeError(
                "Set GITHUB_TOKEN (Copilot model) or FOUNDRY_PROJECT_ENDPOINT + "
                "AZURE_AI_MODEL_DEPLOYMENT_NAME (BYOK Foundry model)."
            )
        await self._client.start()

        common: dict[str, Any] = dict(
            on_permission_request=PermissionHandler.approve_all,
            on_elicitation_request=self._elicitation_handler,
            streaming=True,
            provider=provider,
            model=model,
            working_directory=working_directory or os.path.expanduser("~"),
        )
        if config_directory is not None:
            os.makedirs(config_directory, exist_ok=True)
            common["config_directory"] = config_directory

        if recover:
            try:
                self.session = await self._client.resume_session(session_id, **common)
                logger.info("Resumed Copilot session: %s", session_id)
            except Exception:  # pylint: disable=broad-except
                # No persisted session yet (e.g. the first turn) — create one.
                logger.info(
                    "No session to resume for %s; creating a fresh session.", session_id
                )
                self.session = await self._client.create_session(
                    session_id=session_id, **common
                )
        else:
            self.session = await self._client.create_session(
                session_id=session_id, **common
            )
            logger.info("Created Copilot session: %s", session_id)

        self._unsubscribe = self.session.on(self._on_event)

    async def close(self) -> None:
        """Tear down the subscription and stop the CLI client."""
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:  # pylint: disable=broad-except
                pass
            self._unsubscribe = None
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:  # pylint: disable=broad-except
                pass
            self._client = None

    # -- event pump ----------------------------------------------------------

    def _on_event(self, event: Any) -> None:
        """SDK event callback → push onto the queue (idle terminates a turn)."""
        self._queue.put_nowait(event)
        if getattr(event, "type", None) == SessionEventType.SESSION_IDLE:
            self._queue.put_nowait(_IDLE)

    async def events(self) -> AsyncGenerator[Any, None]:
        """Yield ``SessionEvent`` objects until the agent goes idle."""
        while True:
            item = await self._queue.get()
            if item is _IDLE:
                return
            yield item

    # -- messaging -----------------------------------------------------------

    async def send(self, prompt: str, *, mode: str | None = None) -> str:
        """Send a message. ``mode`` is ``"immediate"`` (steer) or ``"enqueue"``."""
        return await self.session.send(prompt, mode=mode)

    async def abort(self) -> None:
        """Abort the in-flight turn (cooperative cancel of the Copilot agent)."""
        if self.session is not None:
            await self.session.abort()

    # -- elicitation (HITL) bridge ------------------------------------------

    async def _elicitation_handler(self, elicit_ctx: Any) -> Any:
        """Registered ``on_elicitation_request`` callback.

        Surfaces the request to the client (via the task's callback), persists a
        durable marker, then blocks on a Future until the client answers through
        ``answer_elicitation``. On any failure it returns ``cancel`` so the
        Copilot CLI never hangs.
        """
        elicitation_id = str(uuid.uuid4())
        message = ""
        schema: dict = {}
        if isinstance(elicit_ctx, dict):
            message = str(elicit_ctx.get("message", ""))
            schema = dict(elicit_ctx.get("requestedSchema", {}) or {})
        else:  # object form
            message = str(getattr(elicit_ctx, "message", ""))
            schema = dict(getattr(elicit_ctx, "requestedSchema", {}) or {})

        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_elicitations[elicitation_id] = fut

        try:
            if self._on_elicit_request is not None:
                await self._on_elicit_request(elicitation_id, message, schema)
            result = await fut
            return result
        except asyncio.CancelledError:
            return {"action": "cancel"}
        except Exception:  # pylint: disable=broad-except
            logger.exception("elicitation handler failed; cancelling request")
            return {"action": "cancel"}
        finally:
            self._pending_elicitations.pop(elicitation_id, None)

    def answer_elicitation(
        self, elicitation_id: str, action: str, content: dict | None
    ) -> bool:
        """Resolve a parked elicitation Future. Returns False if none is live.

        A False return means the pending elicitation is not held by THIS
        process (e.g. it was raised in a pre-crash lifetime), so the caller
        should fall back to delivering the answer as a normal message.
        """
        fut = self._pending_elicitations.get(elicitation_id)
        if fut is None or fut.done():
            return False
        result: dict[str, Any] = {"action": action}
        if content is not None:
            result["content"] = content
        fut.set_result(result)
        return True

    def has_live_elicitation(self, elicitation_id: str) -> bool:
        """True if the given elicitation is currently parked in this process."""
        fut = self._pending_elicitations.get(elicitation_id)
        return fut is not None and not fut.done()
