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

The sample pins the Copilot SDK version in ``uv.lock`` so the imports
and callback contracts remain reproducible.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copilot import (
    CopilotClient,
    PermissionHandler,
    PostToolUseHookInput,
    PostToolUseHookOutput,
    ProviderConfig,
)
from copilot._telemetry import get_trace_context
from copilot.session_events import SessionEventType

try:
    from .store import todo_fingerprint
except ImportError:
    from store import todo_fingerprint

logger = logging.getLogger(__name__)


class CopilotSessionError(RuntimeError):
    """The Copilot event stream reported a terminal session error."""


class HarnessClosingError(RuntimeError):
    """The harness cannot accept another control request."""


@dataclass
class NativeInputRequest:
    input_id: str
    prompt: str
    mode: str
    acknowledged: asyncio.Future[dict[str, Any]]


@dataclass
class ElicitationDecisionRequest:
    elicitation_id: str
    action: str
    content: dict | None
    acknowledged: asyncio.Future[dict[str, Any]]


@dataclass
class ElicitationRequest:
    elicitation_id: str
    message: str
    schema: dict
    acknowledged: asyncio.Future[None]


@dataclass
class IdleBoundary:
    event: Any


@dataclass
class ResponseBoundary:
    token: object


@dataclass
class TodoCheckpointRequest:
    fingerprint: str | None
    acknowledged: asyncio.Future[None]


@dataclass
class TodoCheckpointDetectionFailure:
    error: BaseException
    acknowledged: asyncio.Future[None]


class CopilotHarness:
    """Owns one Copilot CLI client + session and bridges it to the task."""

    def __init__(self) -> None:
        self._client: CopilotClient | None = None
        self.session: Any = None
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._deferred_events: deque[Any] = deque()
        self._unsubscribe: Callable[[], None] | None = None
        # elicitation_id -> Future[ElicitationResult]
        self._pending_elicitations: dict[str, asyncio.Future] = {}
        self._pending_elicitation_requests: set[asyncio.Future[None]] = set()
        self._workspace: Path | None = None
        self._todo_fingerprint: str | None = None
        self._checkpoint_lock = asyncio.Lock()
        self._pending_checkpoints: set[asyncio.Future[None]] = set()
        self._pending_controls: set[asyncio.Future[dict[str, Any]]] = set()
        self._accepting_controls = True
        self._credential: Any = None
        self._recovered_elicitations: list[dict[str, Any]] = []

    # -- backend selection ---------------------------------------------------

    def _byok_provider(self) -> tuple[Any | None, str | None]:
        """Return (ProviderConfig, model) for BYOK mode, else (None, None).

        The Copilot runtime invokes ``bearer_token_provider`` for every model
        request. Azure Identity owns token caching and refresh.
        """
        endpoint = os.environ.get("AZURE_AI_MODEL_ENDPOINT") or os.environ.get(
            "FOUNDRY_PROJECT_ENDPOINT", ""
        )
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
        if not endpoint or not model:
            return None, None

        from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

        self._credential = DefaultAzureCredential()

        async def token_provider(_args: dict[str, str]) -> str:
            token = await self._credential.get_token("https://ai.azure.com/.default")
            return token.token

        provider = ProviderConfig(
            type="azure",
            base_url=endpoint,
            wire_api="responses",
            bearer_token_provider=token_provider,
        )
        return provider, model

    @staticmethod
    def has_backend() -> bool:
        """True if either a BYOK Foundry model or a GITHUB_TOKEN is configured."""
        byok = bool(
            (
                os.environ.get("AZURE_AI_MODEL_ENDPOINT")
                or os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
            )
            and os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        )
        return byok or bool(os.environ.get("GITHUB_TOKEN"))

    # -- lifecycle -----------------------------------------------------------

    async def start(
        self,
        session_id: str,
        *,
        recover: bool,
        working_directory: str | None = None,
        config_directory: str | None = None,
    ) -> None:
        """Create (fresh) or resume (recovery) the Copilot session.

        :param recover: When True, ``resume_session`` rehydrates the session
            from ``config_dir`` after a crash; when False, a new session is
            created. Resume failures propagate and never create a replacement
            conversation.
        :param config_directory: The Copilot CLI configuration directory where the
            session (its SQLite ``session-store.db`` + ``session-state/`` tree)
            is persisted. Point this at a per-session, durable-store-backed path
            so ``resume_session`` can rehydrate after a container restart.
        """
        self._loop = asyncio.get_running_loop()
        provider, model = self._byok_provider()
        github_token = os.environ.get("GITHUB_TOKEN")
        if provider:
            self._client = CopilotClient()  # BYOK — no token needed
        elif github_token:
            self._client = CopilotClient(github_token=github_token)
        else:
            raise RuntimeError(
                "Set GITHUB_TOKEN (Copilot model) or AZURE_AI_MODEL_DEPLOYMENT_NAME "
                "with AZURE_AI_MODEL_ENDPOINT or FOUNDRY_PROJECT_ENDPOINT "
                "(BYOK Foundry model)."
            )
        try:
            await self._client.start()

            common: dict[str, Any] = dict(
                on_permission_request=PermissionHandler.approve_all,
                on_elicitation_request=self._elicitation_handler,
                streaming=True,
                provider=provider,
                model=model,
                working_directory=working_directory or os.path.expanduser("~"),
                hooks={"on_post_tool_use": self._post_tool_use},
            )
            if config_directory is not None:
                os.makedirs(config_directory, exist_ok=True)
                common["config_directory"] = config_directory

            if recover:
                self.session = await self._client.resume_session(session_id, **common)
                logger.info("Resumed Copilot session: %s", session_id)
            else:
                self.session = await self._client.create_session(
                    session_id=session_id, **common
                )
                logger.info("Created Copilot session: %s", session_id)

            workspace = self.session.workspace_path
            if workspace is None:
                raise RuntimeError(
                    "Copilot did not provide a workspace for todo checkpoints"
                )
            self._workspace = Path(workspace).resolve()
            if config_directory is not None and not self._workspace.is_relative_to(
                Path(config_directory).resolve()
            ):
                raise RuntimeError(
                    "Copilot workspace is outside the snapshot directory"
                )
            self._todo_fingerprint = await asyncio.to_thread(
                todo_fingerprint, self._workspace
            )
            self._unsubscribe = self.session.on(self._on_event)
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Tear down the subscription and stop the CLI client."""
        self._accepting_controls = False
        for pending in self._pending_checkpoints:
            pending.cancel()
        for pending in self._pending_elicitation_requests:
            pending.cancel()
        for pending in self._pending_controls:
            if not pending.done():
                pending.set_exception(HarnessClosingError("Copilot harness is closing"))
        for pending in self._pending_elicitations.values():
            pending.cancel()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:  # pylint: disable=broad-except
                logger.exception("failed to unsubscribe Copilot session events")
            self._unsubscribe = None
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:  # pylint: disable=broad-except
                logger.exception("failed to stop Copilot client")
            self._client = None
        credential = self._credential
        self._credential = None
        if credential is not None:
            await credential.close()
        self._loop = None

    # -- event pump ----------------------------------------------------------

    async def _post_tool_use(
        self, hook: PostToolUseHookInput, context: dict[str, str]
    ) -> PostToolUseHookOutput | None:
        if self._workspace is None:
            raise RuntimeError(
                "Todo checkpoint requested before workspace initialization"
            )
        async with self._checkpoint_lock:
            try:
                fingerprint = await asyncio.to_thread(todo_fingerprint, self._workspace)
            except Exception as exc:
                acknowledged = asyncio.get_running_loop().create_future()
                self._pending_checkpoints.add(acknowledged)
                self._queue.put_nowait(
                    TodoCheckpointDetectionFailure(exc, acknowledged)
                )
                try:
                    await acknowledged
                finally:
                    self._pending_checkpoints.discard(acknowledged)
                raise AssertionError(
                    "Todo checkpoint detection failure was not propagated"
                ) from exc
            if fingerprint == self._todo_fingerprint:
                return None
            acknowledged = asyncio.get_running_loop().create_future()
            self._pending_checkpoints.add(acknowledged)
            # The task consumer persists with its request context and reports
            # failures itself: the SDK logs and swallows hook exceptions.
            self._queue.put_nowait(TodoCheckpointRequest(fingerprint, acknowledged))
            try:
                await acknowledged
                self._todo_fingerprint = fingerprint
            finally:
                self._pending_checkpoints.discard(acknowledged)
        return None

    def _on_event(self, event: Any) -> None:
        """Marshal an SDK reader-thread callback onto the harness event loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug("dropping Copilot event after harness shutdown")
            return
        try:
            if asyncio.get_running_loop() is loop:
                self._enqueue_event(event)
                return
        except RuntimeError:
            pass
        loop.call_soon_threadsafe(self._enqueue_event, event)

    def _enqueue_event(self, event: Any) -> None:
        """Push one session event onto the loop-owned queue."""
        if self._loop is None:
            return
        event_type = getattr(event, "type", None)
        if event_type == SessionEventType.SESSION_IDLE:
            self._queue.put_nowait(IdleBoundary(event))
        else:
            self._queue.put_nowait(event)
        if event_type == SessionEventType.SESSION_ERROR:
            self._queue.put_nowait(
                CopilotSessionError(
                    str(getattr(event, "data", "Copilot session error"))
                )
            )

    async def events(self) -> AsyncGenerator[Any, None]:
        """Yield ``SessionEvent`` objects until the agent goes idle."""
        while True:
            item = await self._next_event()
            if isinstance(item, IdleBoundary):
                yield item.event
                return
            if isinstance(item, CopilotSessionError):
                raise item
            yield item

    async def _next_event(self) -> Any:
        if self._deferred_events:
            return self._deferred_events.popleft()
        return await self._queue.get()

    def _restore_deferred(self, items: list[Any]) -> None:
        self._deferred_events.extendleft(reversed(items))

    # -- messaging -----------------------------------------------------------

    async def send(
        self,
        prompt: str,
        *,
        mode: str | None = None,
        causal_idle: bool = False,
    ) -> str:
        """Send a message. ``mode`` is ``"immediate"`` (steer) or ``"enqueue"``."""
        if self.session is None:
            raise HarnessClosingError("Copilot session is not ready")
        if not causal_idle:
            return await self.session.send(prompt, mode=mode)
        return await self._send_after_stale_idle_barrier(prompt, mode)

    async def _send_after_stale_idle_barrier(
        self, prompt: str, mode: str | None
    ) -> str:
        """Discard every idle boundary preceding the reader-thread response."""
        client = getattr(self.session, "_client", None)
        if client is None or not hasattr(client, "request"):
            return await self._send_with_local_idle_barrier(prompt, mode)

        buffered: list[Any] = []
        loop = asyncio.get_running_loop()
        token = object()

        def mark_response_boundary(_result: Any) -> None:
            loop.call_soon_threadsafe(
                self._queue.put_nowait,
                ResponseBoundary(token),
            )

        params: dict[str, Any] = {
            "sessionId": self.session.session_id,
            "prompt": prompt,
        }
        if mode is not None:
            params["mode"] = mode
        params.update(get_trace_context())
        send_task = asyncio.create_task(
            client.request(
                "session.send",
                params,
                on_response_inline=mark_response_boundary,
            )
        )
        receive_task: asyncio.Task[Any] | None = None
        receive_consumed = True
        try:
            while True:
                receive_task = asyncio.create_task(self._next_event())
                receive_consumed = False
                done, _ = await asyncio.wait(
                    {send_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if send_task in done and send_task.exception() is not None:
                    receive_task.cancel()
                    await asyncio.gather(receive_task, return_exceptions=True)
                    send_task.result()

                if receive_task in done:
                    item = receive_task.result()
                    receive_consumed = True
                    if isinstance(item, ResponseBoundary) and item.token is token:
                        response = await send_task
                        return response["messageId"]
                    if not isinstance(item, IdleBoundary):
                        buffered.append(item)
                else:
                    receive_task.cancel()
                    await asyncio.gather(receive_task, return_exceptions=True)
                    receive_consumed = True
        finally:
            if receive_task is not None and not receive_consumed:
                if not receive_task.done():
                    receive_task.cancel()
                    await asyncio.gather(receive_task, return_exceptions=True)
                elif not receive_task.cancelled():
                    item = receive_task.result()
                    if not (isinstance(item, ResponseBoundary) and item.token is token):
                        buffered.append(item)
            if not send_task.done():
                send_task.cancel()
                await asyncio.gather(send_task, return_exceptions=True)
            self._restore_deferred(buffered)

    async def _send_with_local_idle_barrier(self, prompt: str, mode: str | None) -> str:
        """Fallback for test/session doubles without the pinned RPC client."""
        buffered: list[Any] = []
        while self._deferred_events:
            item = self._deferred_events.popleft()
            if not isinstance(item, IdleBoundary):
                buffered.append(item)
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not isinstance(item, IdleBoundary):
                buffered.append(item)
        try:
            return await self.session.send(prompt, mode=mode)
        finally:
            self._restore_deferred(buffered)

    async def queue_input(
        self, input_id: str, prompt: str, mode: str
    ) -> dict[str, Any]:
        """Queue a native input for durable handling by the task consumer."""
        request = NativeInputRequest(
            input_id,
            prompt,
            mode,
            asyncio.get_running_loop().create_future(),
        )
        return await self._queue_control(request)

    async def queue_elicitation_decision(
        self,
        elicitation_id: str,
        action: str,
        content: dict | None,
    ) -> dict[str, Any]:
        """Queue an HITL decision for context-safe durable handling."""
        request = ElicitationDecisionRequest(
            elicitation_id,
            action,
            content,
            asyncio.get_running_loop().create_future(),
        )
        return await self._queue_control(request)

    async def _queue_control(
        self, request: NativeInputRequest | ElicitationDecisionRequest
    ) -> dict[str, Any]:
        if not self._accepting_controls:
            raise HarnessClosingError("Copilot harness is closing")
        future = request.acknowledged
        self._pending_controls.add(future)
        self._queue.put_nowait(request)
        try:
            return await future
        finally:
            self._pending_controls.discard(future)

    def stop_accepting_controls(self) -> None:
        """Reject new control requests and unblock requests behind an idle."""
        self._accepting_controls = False
        for pending in self._pending_controls:
            if not pending.done():
                pending.set_exception(HarnessClosingError("Copilot harness is closing"))

    async def abort(self) -> None:
        """Abort the in-flight turn (cooperative cancel of the Copilot agent)."""
        if self.session is not None:
            await self.session.abort()

    # -- elicitation (HITL) bridge ------------------------------------------

    async def _elicitation_handler(self, elicit_ctx: Any) -> Any:
        """Registered ``on_elicitation_request`` callback.

        Queues the request for the task consumer to persist and acknowledge,
        then blocks on a Future until the client answers through
        ``answer_elicitation``. On any failure it returns ``cancel`` so the
        Copilot CLI never hangs.
        """
        message = ""
        schema: dict = {}
        if isinstance(elicit_ctx, dict):
            message = str(elicit_ctx.get("message", ""))
            schema = dict(elicit_ctx.get("requestedSchema", {}) or {})
        else:  # object form
            message = str(getattr(elicit_ctx, "message", ""))
            schema = dict(getattr(elicit_ctx, "requestedSchema", {}) or {})
        elicitation_id = str(uuid.uuid4())
        for index, recovered in enumerate(self._recovered_elicitations):
            if (
                recovered.get("message") == message
                and recovered.get("schema") == schema
            ):
                elicitation_id = str(recovered["elicitation_id"])
                self._recovered_elicitations.pop(index)
                break

        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_elicitations[elicitation_id] = fut

        try:
            acknowledged = asyncio.get_running_loop().create_future()
            self._pending_elicitation_requests.add(acknowledged)
            self._queue.put_nowait(
                ElicitationRequest(elicitation_id, message, schema, acknowledged)
            )
            try:
                await acknowledged
            finally:
                self._pending_elicitation_requests.discard(acknowledged)
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

    def bind_recovered_elicitations(self, markers: list[dict[str, Any]]) -> None:
        """Reuse durable ids if the SDK recreates elicitation callbacks."""
        self._recovered_elicitations = [dict(marker) for marker in markers]

    def discard_recovered_elicitation(self, elicitation_id: str) -> None:
        self._recovered_elicitations = [
            marker
            for marker in self._recovered_elicitations
            if marker.get("elicitation_id") != elicitation_id
        ]

    def has_live_elicitation(self, elicitation_id: str) -> bool:
        """True if the given elicitation is currently parked in this process."""
        fut = self._pending_elicitations.get(elicitation_id)
        return fut is not None and not fut.done()
