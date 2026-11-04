# Copyright (c) Microsoft. All rights reserved.

"""Response execution and terminal sequencing for Voice Live Bridge sessions."""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import AsyncIterable, Coroutine
from contextlib import nullcontext
from typing import Any

from azure.ai.agentserver.invocations.voice import (
    AgentError,
    EndCall,
    EndCallMode,
    ResponseCancel,
    ResponseCreated,
    ResponseDone,
    ResponseNone,
    ResponseOutputTextDelta,
    ResponseOutputTextDone,
    Session,
    new_item_id,
    new_response_id,
)

from response_telemetry import ResponseTelemetry
from state import (
    MAX_PENDING_PROACTIVE,
    ApplicationTurn,
    InputOrigin,
    OperationOutcome,
    ProactiveRequest,
    ResponseOperation,
    SessionState,
)

logger = logging.getLogger("voice_live_bridge")

class ResponseCoordinator:
    """Coordinate response tasks for explicit connection-scoped state."""

    def __init__(self) -> None:
        self._detached_tasks: set[asyncio.Task[None]] = set()

    def send_echo(
        self,
        session: Session,
        state: SessionState,
        input_item_id: str,
        chunks: AsyncIterable[str],
        received_at: float,
    ) -> bool:
        """Schedule a cancellable echo without blocking incoming control events."""
        return self.start_response(session, state, input_item_id, chunks, received_at)

    def start_response(
        self,
        session: Session,
        state: SessionState,
        input_item_id: str | None,
        text: str | AsyncIterable[str],
        user_message_received_at: float | None = None,
        *,
        streaming: bool = True,
        voice: dict[str, Any] | None = None,
        response_id: str | None = None,
        response_started: bool = False,
    ) -> bool:
        """Schedule text output while the host continues to receive interruption events."""
        if not state.can_start_response():
            return False
        response_id = response_id or new_response_id()
        input_ids = (input_item_id,) if input_item_id is not None else ()
        operation = ResponseOperation(
            session=session,
            state=state,
            response_id=response_id,
            input_ids=input_ids,
            turn=ApplicationTurn(),
            response_started=response_started,
            telemetry=(
                ResponseTelemetry(response_id, input_item_id, user_message_received_at)
                if input_item_id is not None and user_message_received_at is not None
                else None
            ),
        )
        state.responses[response_id] = operation
        state.track_response(response_id)
        if input_item_id is not None:
            state.input_responses[input_item_id] = response_id
        self._start_task(
            state,
            operation,
            self._run_response(operation, text, streaming, voice),
        )
        return True

    def start_self_cancel(
        self,
        session: Session,
        state: SessionState,
        input_item_id: str,
        text: str,
        user_message_received_at: float,
    ) -> bool:
        """Start a response that requests its own cancellation."""
        if not state.can_start_response():
            return False
        response_id = new_response_id()
        operation = ResponseOperation(
            session=session,
            state=state,
            response_id=response_id,
            input_ids=(input_item_id,),
            turn=ApplicationTurn(),
            response_started=False,
            terminal_event=asyncio.Event(),
            telemetry=ResponseTelemetry(
                response_id,
                input_item_id,
                user_message_received_at,
            ),
        )
        state.responses[operation.response_id] = operation
        state.track_response(operation.response_id)
        state.input_responses[input_item_id] = operation.response_id
        self._start_task(state, operation, self._run_self_cancel(operation, text))
        return True

    def reserve_proactive(self, state: SessionState, text: str) -> str | None:
        """Reserve bounded proactive admission state."""
        if not state.active or len(state.proactive_requests) >= MAX_PENDING_PROACTIVE:
            return None
        response_id = new_response_id()
        state.proactive_requests[response_id] = ProactiveRequest(text)
        return response_id

    async def send_proactive_request(
        self, session: Session, state: SessionState, response_id: str
    ) -> bool:
        """Request proactive admission and roll back the reservation on failure."""
        if not state.active or response_id not in state.proactive_requests:
            state.proactive_requests.pop(response_id, None)
            return False
        try:
            await session.send(
                ResponseCreated(
                    response_id=response_id,
                    admission_timeout_ms=5000,
                    supersede_key="voice-live-bridge-langchain-python",
                )
            )
        except BaseException:
            state.proactive_requests.pop(response_id, None)
            raise
        return True

    async def accept_proactive(
        self, session: Session, state: SessionState, response_id: str
    ) -> None:
        """Start reserved proactive work after Voice Live accepts it."""
        request = state.proactive_requests.pop(response_id, None)
        if request is None or not state.active:
            return
        if not state.can_start_response():
            await session.send(ResponseCancel(response_id=response_id, reason="capacity_exceeded"))
            return
        started = self.start_response(
            session,
            state,
            input_item_id=None,
            text=request.text,
            streaming=False,
            voice=None,
            response_id=response_id,
            response_started=True,
        )
        if not started:
            await session.send(ResponseCancel(response_id=response_id, reason="capacity_exceeded"))

    def barge_in(self, state: SessionState, response_id: str, heard_text: str) -> None:
        """Record what the caller heard and cancel any remaining output."""
        state.record_heard_text(response_id, heard_text)
        self.cancel_response(state, response_id, OperationOutcome.CANCELLED)

    def response_cancelled(self, state: SessionState, response_id: str, heard_text: str) -> None:
        """Synchronize playback state even when generation has already finished."""
        state.record_heard_text(response_id, heard_text)
        operation = state.responses.get(response_id)
        if operation is None:
            return
        operation.select_outcome(OperationOutcome.CANCELLED)
        if operation.terminal_event is not None:
            operation.terminal_event.set()
        elif operation.task is not None:
            operation.task.cancel()

    def response_timeout(
        self,
        state: SessionState,
        response_id: str | None,
        item_ids: tuple[str, ...] | list[str] | None,
    ) -> None:
        """Cancel proactive or active work selected by a timeout event."""
        if response_id is not None:
            state.proactive_requests.pop(response_id, None)
            self.cancel_response(state, response_id, OperationOutcome.TIMEOUT)
            return
        for input_id in item_ids or ():
            if mapped_response_id := state.input_responses.get(input_id):
                self.cancel_response(state, mapped_response_id, OperationOutcome.TIMEOUT)

    @staticmethod
    def cancel_response(state: SessionState, response_id: str, outcome: OperationOutcome) -> None:
        """Select an outcome and cancel one active response."""
        operation = state.responses.get(response_id)
        if operation is None:
            return
        operation.select_outcome(outcome)
        if operation.task is not None:
            operation.task.cancel()

    async def send_none(
        self,
        session: Session,
        input_item_id: str,
        origin: InputOrigin,
        *,
        reason: str = "no_reply_needed",
    ) -> None:
        """Send a terminal response.none decision."""
        del origin
        turn = ApplicationTurn()
        try:
            with turn.activate():
                await session.send(ResponseNone(in_reply_to=(input_item_id,), reason=reason))
            turn.complete(outcome=OperationOutcome.NONE, output_item_count=0)
        except BaseException:
            if not turn.is_completed:
                turn.complete(outcome=OperationOutcome.ERROR, output_item_count=0)
            raise

    async def send_error(self, session: Session, input_item_id: str, origin: InputOrigin) -> None:
        """Send the sample response-scoped error sequence."""
        del origin
        response_id = new_response_id()
        response_started = False
        turn = ApplicationTurn()
        try:
            with turn.activate():
                await session.send(
                    ResponseCreated(response_id=response_id, in_reply_to=(input_item_id,))
                )
                response_started = True
                await session.send(
                    AgentError(
                        code="sample_error",
                        message="The sample emitted the requested error.",
                        response_id=response_id,
                    )
                )
            turn.complete(
                outcome=OperationOutcome.ERROR,
                response_id=response_id,
                output_item_count=0,
            )
        except BaseException:
            if not turn.is_completed:
                turn.complete(
                    outcome=OperationOutcome.ERROR,
                    response_id=response_id if response_started else None,
                    output_item_count=0,
                )
            raise

    async def send_session_error(self, session: Session, origin: InputOrigin) -> None:
        """Send the sample session-scoped error."""
        del origin
        turn = ApplicationTurn()
        try:
            with turn.activate():
                await session.send(
                    AgentError(
                        code="sample_session_error",
                        message="The sample emitted the requested session error.",
                    )
                )
            turn.complete(outcome=OperationOutcome.ERROR, output_item_count=0)
        except BaseException:
            if not turn.is_completed:
                turn.complete(outcome=OperationOutcome.ERROR, output_item_count=0)
            raise

    async def send_end_call(
        self,
        session: Session,
        mode: EndCallMode,
        origin: InputOrigin,
        *,
        reason: str | None = None,
    ) -> None:
        """Send a terminal call instruction."""
        turn = ApplicationTurn()
        try:
            with turn.activate():
                await session.send(
                    EndCall(
                        reason=reason
                        or (
                            "repeated_no_input"
                            if origin is InputOrigin.NO_INPUT
                            else "sample_completed"
                        ),
                        mode=mode,
                    )
                )
            turn.complete(outcome=OperationOutcome.END_CALL, output_item_count=0)
        except BaseException:
            if not turn.is_completed:
                turn.complete(outcome=OperationOutcome.ERROR, output_item_count=0)
            raise

    async def terminate_state(self, state: SessionState, outcome: OperationOutcome) -> None:
        """Cancel and await all operations belonging to one state."""
        tasks = self._mark_terminating(state, outcome)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for operation in tuple(state.responses.values()):
            self._finalize(state, operation, outcome)
        self._clear_state(state)

    def detach_terminating_state(self, state: SessionState, outcome: OperationOutcome) -> None:
        """Synchronously terminate state and track tasks that must finish later."""
        tasks = self._mark_terminating(state, outcome)
        self._clear_state(state)
        for task in tasks:
            self._detached_tasks.add(task)
            task.add_done_callback(self._detached_tasks.discard)

    async def wait_for_detached_tasks(self) -> None:
        """Wait for all transport-detached response tasks."""
        while self._detached_tasks:
            tasks = tuple(self._detached_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._detached_tasks.difference_update(tasks)

    def _start_task(
        self,
        state: SessionState,
        operation: ResponseOperation,
        coroutine: Coroutine[Any, Any, None],
    ) -> None:
        try:
            activation = operation.telemetry.activate() if operation.telemetry else nullcontext()
            with activation:
                task = asyncio.create_task(
                    coroutine,
                    name=f"voice-response-{operation.response_id}",
                )
        except BaseException:
            coroutine.close()
            self._finalize(state, operation, OperationOutcome.ABANDONED)
            raise
        operation.task = task
        task.add_done_callback(
            lambda done: self._task_done(state, operation, done),
            context=contextvars.Context(),
        )

    async def _run_response(
        self,
        operation: ResponseOperation,
        text: str | AsyncIterable[str],
        streaming: bool,
        voice: dict[str, Any] | None,
    ) -> None:
        try:
            if not operation.response_started:
                await operation.session.send(
                    ResponseCreated(
                        response_id=operation.response_id,
                        in_reply_to=operation.input_ids,
                    )
                )
                operation.response_started = True
            with operation.turn.activate():
                await self._send_output(operation, text, streaming, voice)
            operation.select_outcome(OperationOutcome.RESPONSE)
        except asyncio.CancelledError:
            operation.select_outcome(OperationOutcome.CANCELLED)
            raise
        except Exception as exception:
            operation.select_outcome(OperationOutcome.ERROR)
            if operation.telemetry is not None:
                operation.telemetry.record_failure(exception)
            logger.exception("Voice response failed")
            await self._report_failure(operation)

    async def _send_output(
        self,
        operation: ResponseOperation,
        text: str | AsyncIterable[str],
        streaming: bool,
        voice: dict[str, Any] | None,
    ) -> None:
        item_id = new_item_id()
        chunks = self._fixed_chunks(text) if isinstance(text, str) else text
        completed_text = ""
        iterator = aiter(chunks)
        try:
            async for chunk in iterator:
                completed_text += chunk
                if streaming:
                    await operation.session.send(
                        ResponseOutputTextDelta(
                            response_id=operation.response_id,
                            item_id=item_id,
                            delta=chunk,
                            voice=voice,
                        )
                    )
                    # Let control callbacks run even if the producer/send completes synchronously.
                    await asyncio.sleep(0)
        finally:
            # Release producer resources on cancellation or a failed send, not only on exhaustion.
            if close := getattr(iterator, "aclose", None):
                await close()
        await operation.session.send(
            ResponseOutputTextDone(
                response_id=operation.response_id,
                item_id=item_id,
                text=completed_text,
                voice=voice,
            )
        )
        operation.output_item_count = 1
        operation.release_capacity()
        await operation.session.send(ResponseDone(response_id=operation.response_id))
        if operation.telemetry is not None:
            operation.telemetry.record_response_done_sent()

    @staticmethod
    async def _fixed_chunks(text: str) -> AsyncIterable[str]:
        yield text

    async def _run_self_cancel(self, operation: ResponseOperation, text: str) -> None:
        try:
            item_id = new_item_id()
            with operation.turn.activate():
                await operation.session.send(
                    ResponseCreated(
                        response_id=operation.response_id,
                        in_reply_to=operation.input_ids,
                    )
                )
                operation.response_started = True
                await operation.session.send(
                    ResponseOutputTextDelta(
                        response_id=operation.response_id,
                        item_id=item_id,
                        delta=text,
                    )
                )
                await operation.session.send(
                    ResponseCancel(
                        response_id=operation.response_id,
                        reason="sample_self_correction",
                    )
                )
            assert operation.terminal_event is not None
            await operation.terminal_event.wait()
        except asyncio.CancelledError:
            operation.select_outcome(OperationOutcome.CANCELLED)
            raise
        except Exception:
            operation.select_outcome(OperationOutcome.ERROR)
            logger.exception("Self-cancelling response failed")
            await self._report_failure(operation)

    def _task_done(
        self,
        state: SessionState,
        operation: ResponseOperation,
        task: asyncio.Task[None],
    ) -> None:
        if not task.cancelled():
            task.exception()
        self._finalize(state, operation, OperationOutcome.ABANDONED)

    @staticmethod
    def _finalize(
        state: SessionState,
        operation: ResponseOperation,
        fallback: OperationOutcome,
    ) -> None:
        operation.complete(fallback)
        state.responses.pop(operation.response_id, None)
        for input_id in operation.input_ids:
            if state.input_responses.get(input_id) == operation.response_id:
                state.input_responses.pop(input_id, None)

    @staticmethod
    def _mark_terminating(
        state: SessionState, outcome: OperationOutcome
    ) -> list[asyncio.Task[None]]:
        state.terminating = True
        state.proactive_requests.clear()
        tasks: list[asyncio.Task[None]] = []
        for operation in tuple(state.responses.values()):
            operation.select_outcome(outcome)
            if operation.task is not None and not operation.task.done():
                operation.task.cancel()
                tasks.append(operation.task)
        return tasks

    @staticmethod
    def _clear_state(state: SessionState) -> None:
        state.heard_text_by_response.clear()
        state.seen_inputs.clear()

    @staticmethod
    async def _report_failure(operation: ResponseOperation) -> None:
        try:
            await operation.session.send(
                AgentError(
                    code="generation_failed",
                    message="The response could not be generated.",
                    response_id=(operation.response_id if operation.response_started else None),
                )
            )
        except BaseException:
            logger.debug("Could not report response failure")
