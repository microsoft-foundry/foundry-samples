# Copyright (c) Microsoft. All rights reserved.

"""CE transport adapter for the original foreground/background response handler."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    Session,
    UserMessage,
    VoiceAgentServerHost,
    new_response_id,
)

from protocol import ProtocolRuntime
from state import MAX_MESSAGE_CHARACTERS, InputOrigin
from task_store import TaskStore


@dataclass
class Conversation:
    """The request context formerly supplied by the Responses host, scoped to CE."""

    task_store: TaskStore = field(default_factory=TaskStore)
    background_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=20))
    signals: dict[str, asyncio.Event] = field(default_factory=dict)
    heard: dict[str, str] = field(default_factory=dict)


@dataclass
class ResponseContextAdapter:
    response_id: str
    text: str
    history: list[dict[str, Any]]
    conversation: Conversation

    @property
    def task_store(self) -> TaskStore:
        return self.conversation.task_store

    @property
    def background_tasks(self) -> set[asyncio.Task[Any]]:
        return self.conversation.background_tasks

    async def get_input_text(self) -> str:
        return self.text

    async def get_history(self) -> list[dict[str, Any]]:
        return self.history


class VoiceRuntime(ProtocolRuntime):
    """Run the existing handler in a cancellable response task, never the receive loop."""

    def __init__(self, handler: Callable[..., Any]) -> None:
        super().__init__()
        self._handler = handler
        self._conversations: dict[Session, Conversation] = {}
        self._detached_workers: set[asyncio.Task[Any]] = set()

    async def on_session_start(self, session: Session, event: Any) -> None:
        await super().on_session_start(session, event)
        if self._state_for(session) is not None:
            self._conversations.setdefault(session, Conversation())

    async def on_user_message(self, session: Session, event: UserMessage) -> None:
        received_at = time.monotonic()
        state = self._state_for(session)
        if state is None:
            return
        if not await self._claim_input(session, state, event.item_id, InputOrigin.USER):
            if not state.active:
                self._detach_conversation(session)
            return
        text = "".join(part.text for part in event.content if isinstance(part, InputTextPart))
        reason = (
            "empty_input"
            if not text
            else "input_too_large"
            if len(text) > MAX_MESSAGE_CHARACTERS
            else "capacity_exceeded"
            if not state.can_start_response()
            else None
        )
        if reason:
            self._coordinator.schedule_none(
                session, state, event.item_id, InputOrigin.USER, reason=reason
            )
            return
        conversation = self._conversations[session]
        response_id = new_response_id()
        signal = asyncio.Event()
        context = ResponseContextAdapter(
            response_id, text, list(conversation.history), conversation
        )
        conversation.signals[response_id] = signal
        conversation.history.append({"content": [{"type": "input_text", "text": text}]})
        self._coordinator.start_response(
            session,
            state,
            event.item_id,
            self._stream_handler(context, signal),
            received_at,
            response_id=response_id,
        )

    async def _stream_handler(
        self, context: ResponseContextAdapter, signal: asyncio.Event
    ) -> AsyncIterator[str]:
        """Translate original text deltas; keep ack → wait → result behavior unchanged."""
        request = {"input": context.text, "stream": True}
        source = self._handler(request, context, signal)
        output = ""
        last_index = None
        try:
            async for event in source:
                if event["type"] != "response.output_text.delta":
                    continue
                index = event.get("output_index", 0)
                if last_index is not None and index != last_index:
                    output += "\n\n"
                    yield "\n\n"
                last_index = index
                delta = event["delta"]
                output += delta
                yield delta
        finally:
            await source.aclose()
            context.conversation.signals.pop(context.response_id, None)
            heard = context.conversation.heard.get(context.response_id, output)
            if heard:
                context.conversation.history.append(
                    {
                        "response_id": context.response_id,
                        "content": [{"type": "output_text", "text": heard}],
                    }
                )

    def _interrupt(self, session: Session, response_id: str, heard_text: str | None = None) -> None:
        conversation = self._conversations.get(session)
        state = self._state_for(session)
        if conversation is None or state is None:
            return
        if response_id not in state.responses and response_id not in state.heard_text_by_response:
            return
        if signal := conversation.signals.get(response_id):
            signal.set()
        if heard_text is not None:
            conversation.heard[response_id] = heard_text[:MAX_MESSAGE_CHARACTERS]
            while len(conversation.heard) > 64:
                conversation.heard.pop(next(iter(conversation.heard)))
            for item in conversation.history:
                if item.get("response_id") == response_id:
                    item["content"] = [{"type": "output_text", "text": heard_text}]

    async def on_user_barge_in(self, session: Session, event: Any) -> None:
        self._interrupt(session, event.response_id, event.heard_text)
        await super().on_user_barge_in(session, event)

    async def on_response_cancelled(self, session: Session, event: Any) -> None:
        self._interrupt(session, event.response_id, event.heard_text)
        await super().on_response_cancelled(session, event)

    async def on_response_timeout(self, session: Session, event: Any) -> None:
        state = self._state_for(session)
        if state is not None:
            ids = (
                [event.response_id]
                if event.response_id
                else [
                    state.input_responses[item_id]
                    for item_id in event.item_ids or ()
                    if item_id in state.input_responses
                ]
            )
            for response_id in ids:
                self._interrupt(session, response_id)
        await super().on_response_timeout(session, event)

    async def on_user_no_input(self, session: Session, event: Any) -> None:
        if event.count >= 3:
            self._detach_conversation(session)
        await super().on_user_no_input(session, event)

    def _detach_conversation(self, session: Session) -> tuple[asyncio.Task[Any], ...]:
        conversation = self._conversations.pop(session, None)
        if conversation is None:
            return ()
        for signal in conversation.signals.values():
            signal.set()
        for task in conversation.task_store.active_tasks():
            task.cancel_event.set()
        workers = tuple(conversation.background_tasks)
        for worker in workers:
            worker.cancel()
            self._detached_workers.add(worker)
            worker.add_done_callback(self._detached_workers.discard)
        return workers

    async def on_session_end(self, session: Session, event: Any) -> None:
        workers = self._detach_conversation(session)
        await super().on_session_end(session, event)
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    def on_connection_terminating(self, session: Session) -> None:
        self._detach_conversation(session)
        super().on_connection_terminating(session)

    async def close(self) -> None:
        for session in tuple(self._conversations):
            self._detach_conversation(session)
        await super().close()
        if self._detached_workers:
            await asyncio.gather(*tuple(self._detached_workers), return_exceptions=True)


def create_app(
    handler: Callable[..., Any] | None = None, **host_options: Any
) -> VoiceAgentServerHost:
    if handler is None:
        from agent_logic import handler
    runtime = VoiceRuntime(handler)
    app = VoiceAgentServerHost(**host_options)
    runtime.bind(app)
    app.state.voice_runtime = runtime
    return app
