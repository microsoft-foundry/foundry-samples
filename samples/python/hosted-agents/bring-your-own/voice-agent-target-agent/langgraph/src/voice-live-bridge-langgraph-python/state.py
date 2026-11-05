# Copyright (c) Microsoft. All rights reserved.

"""Bounded application state for one Voice Live Bridge connection."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from contextlib import nullcontext
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from azure.ai.agentserver.invocations.voice import Session

from response_telemetry import ResponseTelemetry

MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARACTERS = 24_000
MAX_MESSAGE_CHARACTERS = 8_000
MAX_ACTIVE_RESPONSES = 8
MAX_TERMINAL_SENDS = 8
MAX_PENDING_PROACTIVE = 8
MAX_SEEN_INPUTS = 4096


class InputClaim(Enum):
    INACTIVE = "inactive"
    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    CAPACITY_EXCEEDED = "capacity_exceeded"


class SessionPhase(Enum):
    AWAITING_START = "awaiting_start"
    STARTING = "starting"
    ACTIVE = "active"
    REJECTED = "rejected"
    TERMINATING = "terminating"


class OperationOutcome(Enum):
    """Application-known response outcome used for local cleanup."""

    RESPONSE = "response"
    NONE = "none"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ERROR = "error"
    END_CALL = "end_call"
    TRANSPORT_ERROR = "transport_error"
    ABANDONED = "abandoned"


class InputOrigin(Enum):
    """Origin of one application input decision."""

    USER = "user"
    NO_INPUT = "no_input"
    PROACTIVE = "proactive"


class ApplicationTurn:
    """Minimal application-owned turn bookkeeping for Bridge Protocol 1.0."""

    def __init__(self) -> None:
        self.is_completed = False

    def activate(self) -> Any:
        return nullcontext()

    def complete(self, **fields: Any) -> None:
        del fields
        self.is_completed = True


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """One bounded message supplied to the model backend."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(slots=True)
class ConversationTurn:
    response_id: str
    prompt: str
    answer: str


class ConversationHistory:
    """Connection-scoped history reconciled to caller-heard text."""

    def __init__(self) -> None:
        self.generation_gate = asyncio.Lock()
        self._turns: list[ConversationTurn] = []
        self._lock = threading.Lock()

    def create_request(self, prompt: str) -> tuple[ModelMessage, ...]:
        with self._lock:
            messages = [
                message
                for turn in self._turns
                for message in (
                    ModelMessage("user", turn.prompt),
                    ModelMessage("assistant", turn.answer),
                )
                if message.content
            ]
            return (*messages, ModelMessage("user", self._bound(prompt)))

    def commit(self, response_id: str, prompt: str, answer: str) -> None:
        with self._lock:
            if any(turn.response_id == response_id for turn in self._turns):
                return
            self._turns.append(
                ConversationTurn(response_id, self._bound(prompt), self._bound(answer))
            )
            self._trim()

    def reconcile(self, response_id: str, prompt: str | None, heard_text: str) -> None:
        with self._lock:
            for index, turn in enumerate(self._turns):
                if turn.response_id == response_id:
                    if heard_text:
                        self._turns[index] = ConversationTurn(
                            response_id,
                            turn.prompt,
                            self._bound(heard_text),
                        )
                    else:
                        del self._turns[index]
                    self._trim()
                    return
            if prompt is not None and heard_text:
                self._turns.append(
                    ConversationTurn(
                        response_id,
                        self._bound(prompt),
                        self._bound(heard_text),
                    )
                )
                self._trim()

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def _trim(self) -> None:
        while (
            len(self._turns) * 2 > MAX_HISTORY_MESSAGES
            or sum(len(turn.prompt) + len(turn.answer) for turn in self._turns)
            > MAX_HISTORY_CHARACTERS
        ):
            del self._turns[0]

    @staticmethod
    def _bound(value: str) -> str:
        return value[:MAX_MESSAGE_CHARACTERS]


@dataclass(frozen=True, slots=True)
class ProactiveRequest:
    text: str
    use_model: bool


@dataclass(slots=True)
class ResponseOperation:
    session: Session
    state: "SessionState"
    response_id: str
    input_ids: tuple[str, ...]
    turn: ApplicationTurn
    prompt: str | None
    response_started: bool
    task: asyncio.Task[None] | None = None
    terminal_event: asyncio.Event | None = None
    output_item_count: int = 0
    history_committed: bool = False
    capacity_released: bool = False
    outcome: OperationOutcome | None = None
    telemetry: ResponseTelemetry | None = None

    def select_outcome(self, outcome: OperationOutcome) -> None:
        """Keep the first application-known terminal outcome."""
        if self.outcome is None:
            self.outcome = outcome

    def commit_history(self, assistant_message: str) -> None:
        """Commit one model turn after output completed."""
        if self.history_committed or self.prompt is None or not assistant_message:
            return
        self.history_committed = True
        self.state.history.commit(self.response_id, self.prompt, assistant_message)

    def complete(self, fallback: OperationOutcome) -> None:
        """Complete application-owned response telemetry exactly once."""
        self.select_outcome(fallback)
        if self.telemetry is not None:
            assert self.outcome is not None
            self.telemetry.record_outcome(self.outcome.value)

    def release_capacity(self) -> None:
        """Allow a new response to start before this task's done callback runs."""
        self.capacity_released = True


@dataclass(slots=True)
class SessionState:
    history: ConversationHistory = field(default_factory=ConversationHistory)
    responses: dict[str, ResponseOperation] = field(default_factory=dict)
    input_responses: dict[str, str] = field(default_factory=dict)
    proactive_requests: dict[str, ProactiveRequest] = field(default_factory=dict)
    seen_inputs: set[bytes] = field(default_factory=set)
    phase: SessionPhase = SessionPhase.AWAITING_START

    @property
    def terminating(self) -> bool:
        return self.phase is SessionPhase.TERMINATING

    @terminating.setter
    def terminating(self, value: bool) -> None:
        if value:
            self.phase = SessionPhase.TERMINATING

    @property
    def active(self) -> bool:
        return self.phase is SessionPhase.ACTIVE

    @property
    def active_response_count(self) -> int:
        """Count operations that still occupy one response-capacity slot."""
        return sum(not operation.capacity_released for operation in self.responses.values())

    @property
    def terminal_send_count(self) -> int:
        """Count released operations whose terminal send has not finalized."""
        return sum(operation.capacity_released for operation in self.responses.values())

    def can_start_response(self) -> bool:
        """Return whether this active connection can reserve another response slot."""
        return (
            self.active
            and self.active_response_count < MAX_ACTIVE_RESPONSES
            and self.terminal_send_count < MAX_TERMINAL_SENDS
        )

    def try_begin_start(self) -> bool:
        if self.phase is not SessionPhase.AWAITING_START:
            return False
        self.phase = SessionPhase.STARTING
        return True

    def activate(self) -> None:
        if self.phase is SessionPhase.STARTING:
            self.phase = SessionPhase.ACTIVE

    def reject(self) -> None:
        if self.phase is SessionPhase.STARTING:
            self.phase = SessionPhase.REJECTED

    def claim_input(self, item_id: str) -> InputClaim:
        """Claim an input once without forgetting IDs during this connection."""
        if not self.active:
            return InputClaim.INACTIVE
        digest = hashlib.sha256(item_id.encode("utf-8")).digest()
        if digest in self.seen_inputs:
            return InputClaim.DUPLICATE
        if len(self.seen_inputs) >= MAX_SEEN_INPUTS:
            return InputClaim.CAPACITY_EXCEEDED
        self.seen_inputs.add(digest)
        return InputClaim.CLAIMED


class SessionStore:
    """Own the mapping from transport sessions to connection state."""

    def __init__(self) -> None:
        self._states: dict[Session, SessionState] = {}

    def get_or_create(self, session: Session) -> SessionState:
        """Return existing state or create state for a new connection."""
        return self._states.setdefault(session, SessionState())

    def active(self, session: Session) -> SessionState | None:
        """Return active state, or None for early and late callbacks."""
        state = self._states.get(session)
        return state if state is not None and state.active else None

    def remove(self, session: Session) -> SessionState | None:
        """Remove and return one connection state."""
        return self._states.pop(session, None)

    def drain(self) -> tuple[SessionState, ...]:
        """Atomically detach a snapshot of all connection states."""
        states = tuple(self._states.values())
        self._states.clear()
        return states
