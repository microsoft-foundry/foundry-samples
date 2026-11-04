# Copyright (c) Microsoft. All rights reserved.

"""Application-owned Voice Live Bridge Protocol 1.0 runtime."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from azure.ai.agentserver.invocations.voice import (
    EndCallMode,
    InputTextPart,
    ResponseAccepted,
    ResponseCancelled,
    ResponseDropped,
    ResponseTimeout,
    Session,
    SessionDisconnected,
    SessionEnd,
    SessionReady,
    SessionRejected,
    SessionStart,
    UserBargeIn,
    UserMessage,
    UserNoInput,
    UserSpeechStarted,
    VoiceAgentServerHost,
)

from response_coordinator import ResponseCoordinator
from state import (
    MAX_MESSAGE_CHARACTERS,
    InputClaim,
    InputOrigin,
    OperationOutcome,
    SessionState,
    SessionStore,
)

logger = logging.getLogger("voice_live_bridge")

SUPPORTED_PROTOCOL_VERSION = "1.0"
IDLE_REMINDER_TEXT = "Are you still there?"


class VoiceRuntime:
    """Application-owned lifecycle for typed Voice Live Bridge callbacks."""

    def __init__(self) -> None:
        self._store = SessionStore()
        self._coordinator = ResponseCoordinator()
        self._closed = False

    def bind(self, app: VoiceAgentServerHost) -> None:
        """Register all callbacks on one Voice host."""

        @app.on_session_start
        async def session_start(session: Session, event: SessionStart) -> None:
            await self.on_session_start(session, event)

        @app.on_user_message
        async def user_message(session: Session, event: UserMessage) -> None:
            await self.on_user_message(session, event)

        @app.on_user_no_input
        async def user_no_input(session: Session, event: UserNoInput) -> None:
            await self.on_user_no_input(session, event)

        @app.on_user_speech_started
        async def user_speech_started(session: Session, event: UserSpeechStarted) -> None:
            await self.on_user_speech_started(session, event)

        @app.on_user_barge_in
        async def user_barge_in(session: Session, event: UserBargeIn) -> None:
            await self.on_user_barge_in(session, event)

        @app.on_response_accepted
        async def response_accepted(session: Session, event: ResponseAccepted) -> None:
            await self.on_response_accepted(session, event)

        @app.on_response_dropped
        async def response_dropped(session: Session, event: ResponseDropped) -> None:
            await self.on_response_dropped(session, event)

        @app.on_response_cancelled
        async def response_cancelled(session: Session, event: ResponseCancelled) -> None:
            await self.on_response_cancelled(session, event)

        @app.on_response_timeout
        async def response_timeout(session: Session, event: ResponseTimeout) -> None:
            await self.on_response_timeout(session, event)

        @app.on_session_end
        async def session_end(session: Session, event: SessionEnd) -> None:
            await self.on_session_end(session, event)

        @app.on_disconnect
        async def disconnected(session: Session, event: SessionDisconnected) -> None:
            del session
            logger.info("Voice transport disconnected; close_code=%d", event.code)

        @app.on_connection_terminating
        def terminating(session: Session) -> None:
            self.on_connection_terminating(session)

        @app.shutdown_handler
        async def shutdown() -> None:
            await self.close()

    async def on_session_start(self, session: Session, event: SessionStart) -> None:
        state = self._store.get_or_create(session)
        if not state.try_begin_start():
            logger.warning("Ignoring duplicate or late session.start")
            return
        if event.protocol_version != SUPPORTED_PROTOCOL_VERSION:
            state.reject()
            await session.send(SessionRejected(code="protocol_mismatch", retriable=False))
            return
        if os.getenv("VOICE_SAMPLE_REJECT_START", "").lower() == "true":
            state.reject()
            await session.send(
                SessionRejected(
                    code="startup_failed",
                    retriable=True,
                    message="VOICE_SAMPLE_REJECT_START is enabled.",
                )
            )
            return
        try:
            await session.send(SessionReady())
            state.activate()
        except BaseException:
            state.terminating = True
            raise

    async def on_user_message(self, session: Session, event: UserMessage) -> None:
        """Stream the same short children's story for every valid text message."""
        received_at = time.monotonic()
        state = self._state_for(session)
        if state is None:
            return
        if not await self._claim_input(session, state, event.item_id, InputOrigin.USER):
            return

        text = "".join(part.text for part in event.content if isinstance(part, InputTextPart))
        if not text or len(text) > MAX_MESSAGE_CHARACTERS:
            await self._coordinator.send_none(
                session,
                event.item_id,
                InputOrigin.USER,
                reason="empty_input" if not text else "input_too_large"
            )
            return
        if not state.can_start_response():
            await self._coordinator.send_none(
                session, event.item_id, InputOrigin.USER, reason="capacity_exceeded"
            )
            return

        story = (
            "Once a little rabbit found a lonely star. She carried it up the tallest hill, "
            "where friendly fireflies helped it shine again. "
            "That night, everyone dreamed of kindness and adventure."
        )

        async def stream_story() -> AsyncIterator[str]:
            # Replace this generator with your own asynchronous text source.
            for index, word in enumerate(story.split(" ")):
                await asyncio.sleep(0)
                yield (" " if index else "") + word

        self._coordinator.send_echo(session, state, event.item_id, stream_story(), received_at)

    async def on_user_no_input(self, session: Session, event: UserNoInput) -> None:
        state = self._state_for(session)
        if state is None:
            return
        if not await self._claim_input(session, state, event.item_id, InputOrigin.NO_INPUT):
            return
        if event.count >= 3:
            await self._coordinator.terminate_state(state, OperationOutcome.END_CALL)
            await self._coordinator.send_end_call(
                session, EndCallMode.DRAIN, InputOrigin.NO_INPUT
            )
            return
        if not state.can_start_response():
            await self._coordinator.send_none(
                session,
                event.item_id,
                InputOrigin.NO_INPUT,
                reason="capacity_exceeded",
            )
            return
        self._coordinator.start_response(
            session,
            state,
            event.item_id,
            text=IDLE_REMINDER_TEXT,
            streaming=False,
            voice=None,
        )

    async def on_user_speech_started(self, session: Session, event: UserSpeechStarted) -> None:
        del event
        if self._state_for(session) is not None:
            logger.debug("Caller speech started")

    async def on_user_barge_in(self, session: Session, event: UserBargeIn) -> None:
        state = self._state_for(session)
        if state is not None:
            self._coordinator.barge_in(state, event.response_id, event.heard_text)

    async def on_response_accepted(self, session: Session, event: ResponseAccepted) -> None:
        state = self._state_for(session)
        if state is not None:
            await self._coordinator.accept_proactive(session, state, event.response_id)

    async def on_response_dropped(self, session: Session, event: ResponseDropped) -> None:
        state = self._state_for(session)
        if state is not None:
            state.proactive_requests.pop(event.response_id, None)

    async def on_response_cancelled(self, session: Session, event: ResponseCancelled) -> None:
        state = self._state_for(session)
        if state is not None:
            self._coordinator.response_cancelled(state, event.response_id, event.heard_text)

    async def on_response_timeout(self, session: Session, event: ResponseTimeout) -> None:
        state = self._state_for(session)
        if state is not None:
            self._coordinator.response_timeout(state, event.response_id, event.item_ids)

    async def on_session_end(self, session: Session, event: SessionEnd) -> None:
        del event
        state = self._store.remove(session)
        if state is not None:
            await self._coordinator.terminate_state(state, OperationOutcome.END_CALL)

    def on_connection_terminating(self, session: Session) -> None:
        state = self._store.remove(session)
        if state is not None:
            self._coordinator.detach_terminating_state(state, OperationOutcome.TRANSPORT_ERROR)

    def _state_for(self, session: Session) -> SessionState | None:
        return self._store.active(session)

    async def _claim_input(
        self,
        session: Session,
        state: SessionState,
        item_id: str,
        origin: InputOrigin,
    ) -> bool:
        claim = state.claim_input(item_id)
        if claim is InputClaim.CLAIMED:
            return True
        if claim is InputClaim.INACTIVE:
            return False
        if claim is InputClaim.DUPLICATE:
            logger.warning("Ignoring duplicate Voice input item")
            return False
        await self._coordinator.terminate_state(state, OperationOutcome.END_CALL)
        await self._coordinator.send_end_call(
            session,
            EndCallMode.DRAIN,
            origin,
            reason="session_input_limit",
        )
        return False

    async def close(self) -> None:
        """Cancel all sessions and finish detached response tasks once."""
        if self._closed:
            return
        self._closed = True
        states = self._store.drain()
        for state in states:
            await self._coordinator.terminate_state(state, OperationOutcome.CANCELLED)
        await self._coordinator.wait_for_detached_tasks()


def create_app(**host_options: Any) -> VoiceAgentServerHost:
    """Create a Voice host with isolated application state."""
    runtime = VoiceRuntime()
    app = VoiceAgentServerHost(**host_options)
    runtime.bind(app)
    app.state.voice_runtime = runtime
    return app
