"""Bind the Router/Worker workflow to the existing native CE runtime."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    ResponseCancelled,
    ResponseDone,
    ResponseOutputTextDelta,
    Session,
    SessionEnd,
    SessionStart,
    UserBargeIn,
    UserMessage,
    UserNoInput,
    VoiceAgentServerHost,
    new_response_id,
)

from agent_logic import Conversation, ForegroundBackgroundAgent, HistoryEntry, Turn
from state import MAX_MESSAGE_CHARACTERS, InputOrigin, OperationOutcome, SessionState
from task_store import TaskStatus
from voice_runtime import VoiceRuntime


class HistorySession:
    """Record only successfully sent output, not merely generated text."""

    def __init__(
        self,
        session: Session,
        state: SessionState,
        conversation: Conversation,
        turn: Turn,
    ) -> None:
        self.session = session
        self.state = state
        self.conversation = conversation
        self.turn = turn

    async def send(self, message: Any) -> None:
        await self.session.send(message)
        operation = self.state.responses.get(self.turn.response_id)
        if not self.state.active or (operation and operation.cancellation_requested):
            return
        if isinstance(message, ResponseOutputTextDelta):
            entry = next(
                (
                    entry
                    for entry in self.conversation.history
                    if entry.response_id == self.turn.response_id
                ),
                None,
            )
            if entry is None:
                entry = HistoryEntry("assistant", "", self.turn.response_id)
                self.conversation.history.append(entry)
            entry.content += message.delta
        elif isinstance(message, ResponseDone):
            for task_id in self.turn.delivered_task_ids:
                task = self.conversation.tasks.get(task_id)
                if task and task.status is TaskStatus.COMPLETED:
                    task.status = TaskStatus.DELIVERED


class ConversationRuntime(VoiceRuntime):
    def __init__(self, agent: ForegroundBackgroundAgent) -> None:
        super().__init__()
        self.agent = agent
        self.conversations: dict[Session, Conversation] = {}
        self._shutdown: asyncio.Task[None] | None = None

    async def on_session_start(self, session: Session, event: SessionStart) -> None:
        already_active = self._state_for(session) is not None
        await super().on_session_start(session, event)
        if not already_active and self._state_for(session) is not None and event.greeting:
            conversation = self.conversations.setdefault(session, Conversation())
            conversation.history.append(HistoryEntry("assistant", event.greeting))

    async def on_user_message(self, session: Session, event: UserMessage) -> None:
        received_at = time.monotonic()
        state = self._state_for(session)
        if state is None:
            return
        if not await self._claim_input(session, state, event.item_id, InputOrigin.USER):
            if not state.active:
                self._detach(session)
            return
        text = "".join(part.text for part in event.content if isinstance(part, InputTextPart))
        if any(not isinstance(part, InputTextPart) for part in event.content):
            reason = "unsupported_input"
        elif not text.strip() or len(text) > MAX_MESSAGE_CHARACTERS:
            reason = "empty_input" if not text.strip() else "input_too_large"
        elif not state.can_start_response():
            reason = "capacity_exceeded"
        else:
            conversation = self.conversations.setdefault(session, Conversation())
            turn = Turn(new_response_id())
            self._coordinator.start_response(
                HistorySession(session, state, conversation, turn),
                state,
                event.item_id,
                self.agent.respond(conversation, turn, text),
                received_at,
                response_id=turn.response_id,
            )
            return
        self._coordinator.schedule_none(
            session,
            state,
            event.item_id,
            InputOrigin.USER,
            reason=reason,
        )
        if not state.active:
            self._detach(session)

    def _reconcile(self, session: Session, response_id: str, heard_text: str) -> None:
        state = self._state_for(session)
        conversation = self.conversations.get(session)
        if state and conversation and response_id in state.heard_text_by_response:
            conversation.reconcile(response_id, heard_text[:MAX_MESSAGE_CHARACTERS])

    async def on_user_barge_in(self, session: Session, event: UserBargeIn) -> None:
        self._reconcile(session, event.response_id, event.heard_text)
        await super().on_user_barge_in(session, event)

    async def on_response_cancelled(self, session: Session, event: ResponseCancelled) -> None:
        self._reconcile(session, event.response_id, event.heard_text)
        await super().on_response_cancelled(session, event)

    def _detach(self, session: Session) -> None:
        conversation = self.conversations.pop(session, None)
        if conversation is not None:
            conversation.cancel_workers()

    async def on_user_no_input(self, session: Session, event: UserNoInput) -> None:
        if event.count >= 3:
            state = self._state_for(session)
            if state is None:
                return
            if not await self._claim_input(session, state, event.item_id, InputOrigin.NO_INPUT):
                if not state.active:
                    self._detach(session)
                return
            self._detach(session)
            self._coordinator.detach_terminating_state(state, OperationOutcome.END_CALL)
            self._coordinator.schedule_end_call(session, state, InputOrigin.NO_INPUT)
            return
        await super().on_user_no_input(session, event)
        if self._state_for(session) is None:
            self._detach(session)

    async def on_session_end(self, session: Session, event: SessionEnd) -> None:
        self._detach(session)
        await super().on_session_end(session, event)

    def on_connection_terminating(self, session: Session) -> None:
        self._detach(session)
        super().on_connection_terminating(session)

    async def close(self) -> None:
        if self._shutdown is None:
            self._shutdown = asyncio.create_task(self._close())
        await asyncio.shield(self._shutdown)

    async def _close(self) -> None:
        for session in tuple(self.conversations):
            self._detach(session)
        await super().close()
        await self.agent.close()


def create_app(agent: ForegroundBackgroundAgent, **options: Any) -> VoiceAgentServerHost:
    runtime = ConversationRuntime(agent)
    app = VoiceAgentServerHost(**options)
    runtime.bind(app)
    app.state.voice_runtime = runtime
    return app
