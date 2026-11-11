# Copyright (c) Microsoft. All rights reserved.

"""Response execution and terminal sequencing for Voice Live Bridge sessions."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import sys
from collections.abc import AsyncIterable, Coroutine, Mapping
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
    ResponseOutputDataDone,
    ResponseOutputTextDelta,
    ResponseOutputTextDone,
    Session,
    new_item_id,
    new_response_id,
)

from response_telemetry import ResponseTelemetry
from state import (
    MAX_PENDING_PROACTIVE,
    MAX_TERMINAL_SENDS,
    ApplicationTurn,
    InputOrigin,
    OperationOutcome,
    ProactiveRequest,
    ResponseOperation,
    SessionState,
)

logger = logging.getLogger("voice_live_bridge")
MAX_OUTPUT_BYTES = 512 * 1024
MAX_OUTPUT_CHUNKS = 4096

OutputChunk = str | Mapping[str, Any]
MAX_DATA_BYTES = 65_536

class ResponseCoordinator:
    """Coordinate response tasks for explicit connection-scoped state."""

    def __init__(self) -> None:
        self._detached_tasks: set[asyncio.Task[None]] = set()

    def send_echo(
        self,
        session: Session,
        state: SessionState,
        input_item_id: str,
        chunks: AsyncIterable[OutputChunk],
        received_at: float,
    ) -> bool:
        """Schedule a cancellable echo without blocking incoming control events."""
        return self.start_response(session, state, input_item_id, chunks, received_at)

    def start_response(
        self,
        session: Session,
        state: SessionState,
        input_item_id: str | None,
        text: OutputChunk | AsyncIterable[OutputChunk],
        user_message_received_at: float | None = None,
        *,
        streaming: bool = True,
        voice: dict[str, Any] | None = None,
        response_id: str | None = None,
        response_started: bool = False,
    ) -> bool:
        """Schedule output while the host continues to receive interruption events."""
        if not state.can_start_response():
            return False
        response_id = response_id or new_response_id()
        input_ids = (input_item_id,) if input_item_id is not None else ()
        initialization_error: BaseException | None = None
        # Retain the accepted source as the close target if iterator setup fails.
        iterator = self._fixed_chunks(text) if isinstance(text, (str, Mapping)) else text
        try:
            iterator = aiter(iterator)
        except (Exception, asyncio.CancelledError) as error:
            # Keep source setup failures inside the ordered, tracked response lifecycle.
            initialization_error = error
        operation = ResponseOperation(
            session=session,
            state=state,
            response_id=response_id,
            input_ids=input_ids,
            turn=ApplicationTurn(),
            response_started=response_started,
            output_iterator=iterator,
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
            self._run_response(operation, text, streaming, voice, initialization_error),
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
                    supersede_key="voice-live-bridge-basic-python",
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
            self._cancel_accepted_proactive(session, state, response_id)
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
            self._cancel_accepted_proactive(session, state, response_id)

    def _cancel_accepted_proactive(
        self, session: Session, state: SessionState, response_id: str,
    ) -> None:
        # An accepted admission already owns a wire generation. Keep its cancellation
        # request off receive dispatch, and wait for the winning protocol outcome.
        if state.terminal_send_count >= MAX_TERMINAL_SENDS:
            self.detach_terminating_state(state, OperationOutcome.END_CALL)
            self.schedule_end_call(
                session, state, InputOrigin.PROACTIVE, reason="capacity_exceeded",
            )
            return
        operation = ResponseOperation(
            session, state, response_id, (), ApplicationTurn(), True,
            terminal_event=asyncio.Event(), capacity_released=True,
        )
        state.responses[response_id] = operation
        state.track_response(response_id)

        async def cancel() -> None:
            await state.generation_gate.acquire()
            operation.generation_acquired = True
            await self._send(operation, ResponseCancel(
                response_id=response_id, reason="capacity_exceeded",
            ))
            assert operation.terminal_event is not None
            await operation.terminal_event.wait()

        self._start_task(state, operation, cancel())

    def barge_in(self, state: SessionState, response_id: str, heard_text: str) -> None:
        """Record what the caller heard and cancel any remaining output."""
        state.record_heard_text(response_id, heard_text)
        self.cancel_response(state, response_id, OperationOutcome.CANCELLED)

    def response_cancelled(self, state: SessionState, response_id: str, heard_text: str) -> None:
        """Synchronize playback state even when generation has already finished."""
        state.record_heard_text(response_id, heard_text)
        self.cancel_response(state, response_id, OperationOutcome.CANCELLED)

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
        operation = state.responses.get(response_id)
        if operation is not None:
            operation.request_stop(outcome)

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
        """Retain the workers before joining; cancelling a join does not cancel cleanup."""
        self.detach_terminating_state(state, outcome)
        tasks = [operation.task for operation in tuple(state.responses.values())
                 if operation.task is not None]
        if tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)

    def detach_terminating_state(self, state: SessionState, outcome: OperationOutcome) -> None:
        state.terminating = True
        state.proactive_requests.clear()
        for operation in tuple(state.responses.values()):
            operation.request_stop(outcome)
            if operation.task is not None:
                self._retain_task(operation.task)
        self._clear_state(state)

    def _retain_task(self, task: asyncio.Task[None]) -> None:
        self._detached_tasks.add(task)
        task.add_done_callback(self._detached_tasks.discard)

    async def wait_for_detached_tasks(self) -> None:
        while self._detached_tasks:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._detached_tasks)),
                return_exceptions=True,
            )

    def schedule_none(
        self, session: Session, state: SessionState, input_item_id: str,
        origin: InputOrigin, *, reason: str,
    ) -> None:
        if not state.active:
            return
        if state.terminal_send_count >= MAX_TERMINAL_SENDS:
            self.detach_terminating_state(state, OperationOutcome.END_CALL)
            self.schedule_end_call(session, state, origin, reason="capacity_exceeded")
            return
        operation = ResponseOperation(
            session, state, new_response_id(), (input_item_id,), ApplicationTurn(), False,
            capacity_released=True,
        )
        state.responses[operation.response_id] = operation
        state.input_responses[input_item_id] = operation.response_id

        async def decline() -> None:
            await self._await_resolution(operation)
            self._ensure_writable(operation)
            await self.send_none(session, input_item_id, origin, reason=reason)
            if not operation.cancellation_requested:
                operation.terminal_sent = True
                operation.select_outcome(OperationOutcome.NONE)

        self._start_task(state, operation, decline())

    def schedule_end_call(
        self, session: Session, state: SessionState, origin: InputOrigin,
        *, reason: str | None = None,
    ) -> None:
        operation = ResponseOperation(
            session, state, new_response_id(), (), ApplicationTurn(), False,
            capacity_released=True,
        )
        state.responses[operation.response_id] = operation

        async def end_call() -> None:
            await self.send_end_call(session, EndCallMode.DRAIN, origin, reason=reason)
            operation.terminal_sent = True
            operation.select_outcome(OperationOutcome.END_CALL)

        self._start_task(state, operation, end_call(), requires_active=False)
        assert operation.task is not None
        self._retain_task(operation.task)

    @staticmethod
    async def _await_resolution(operation: ResponseOperation) -> None:
        if operation.previous_resolution is not None:
            await asyncio.shield(operation.previous_resolution)

    @staticmethod
    async def _finish_resolution(operation: ResponseOperation) -> None:
        if operation.resolution_done is not None and not operation.resolution_done.done():
            await ResponseCoordinator._await_resolution(operation)
            operation.resolution_done.set_result(None)

    @staticmethod
    def _ensure_writable(operation: ResponseOperation) -> None:
        if (
            operation.cancellation_requested or operation.terminal_sent
            or not operation.state.active
        ):
            raise asyncio.CancelledError()

    async def _send(self, operation: ResponseOperation, message: Any) -> None:
        self._ensure_writable(operation)
        await operation.session.send(message)

    @staticmethod
    async def _close_output(operation: ResponseOperation) -> None:
        iterator, operation.output_iterator = operation.output_iterator, None
        if iterator is None or (closer := getattr(iterator, "aclose", None)) is None:
            return
        primary_error = sys.exception()
        operation.closing = True
        try:
            await closer()
        except (Exception, asyncio.CancelledError) as error:
            if primary_error is None or isinstance(primary_error, GeneratorExit):
                raise
            logger.warning("Producer close failed; error_type=%s", type(error).__name__)
        finally:
            operation.closing = False

    def _start_task(
        self, state: SessionState, operation: ResponseOperation,
        coroutine: Coroutine[Any, Any, None], *, requires_active: bool = True,
    ) -> None:
        if operation.input_ids:
            operation.previous_resolution = state.input_resolution_tail
            operation.resolution_done = asyncio.get_running_loop().create_future()
            state.input_resolution_tail = operation.resolution_done

        async def run() -> None:
            operation.running = True
            try:
                if requires_active:
                    self._ensure_writable(operation)
                elif operation.cancellation_requested:
                    raise asyncio.CancelledError()
                await coroutine
            finally:
                operation.finalizing = True
                coroutine.close()
                try:
                    # Ordering records the input decision, not completion of resource cleanup.
                    await self._finish_resolution(operation)
                finally:
                    try:
                        await self._close_output(operation)
                    finally:
                        operation.release_generation()

        wrapper = run()
        try:
            activation = operation.telemetry.activate() if operation.telemetry else nullcontext()
            with activation:
                task = asyncio.create_task(wrapper, name=f"voice-response-{operation.response_id}")
        except BaseException:
            wrapper.close()
            coroutine.close()
            self._finalize(state, operation, OperationOutcome.ABANDONED)
            raise
        operation.task = task
        task.add_done_callback(
            lambda done: self._task_done(state, operation, done), context=contextvars.Context(),
        )

    async def _run_response(
        self,
        operation: ResponseOperation,
        text: OutputChunk | AsyncIterable[OutputChunk],
        streaming: bool,
        voice: dict[str, Any] | None,
        initialization_error: BaseException | None = None,
    ) -> None:
        try:
            await self._await_resolution(operation)
            await operation.state.generation_gate.acquire()
            operation.generation_acquired = True
            self._ensure_writable(operation)
            if not operation.response_started:
                await self._send(operation,
                    ResponseCreated(
                        response_id=operation.response_id,
                        in_reply_to=operation.input_ids,
                    )
                )
                operation.response_started = True
                await self._finish_resolution(operation)
            if initialization_error is not None:
                raise initialization_error
            with operation.turn.activate():
                await self._send_output(operation, text, streaming, voice)
            operation.select_outcome(OperationOutcome.RESPONSE)
        except asyncio.CancelledError as error:
            if operation.cancellation_requested or not operation.state.active:
                raise
            if operation.telemetry is not None:
                operation.telemetry.record_failure(error)
            await self._report_failure(operation)
        except Exception as exception:
            if operation.telemetry is not None:
                operation.telemetry.record_failure(exception)
            logger.warning("Voice response failed; error_type=%s", type(exception).__name__)
            await self._report_failure(operation)

    async def _send_output(
        self,
        operation: ResponseOperation,
        text: OutputChunk | AsyncIterable[OutputChunk],
        streaming: bool,
        voice: dict[str, Any] | None,
    ) -> None:
        item_id: str | None = None
        del text  # The accepted iterator is owned before the task starts.
        completed_text = ""
        output_bytes = 0
        output_chunks = 0
        data_bytes = 0

        async def finish_text() -> None:
            nonlocal item_id, completed_text
            if item_id is not None:
                await self._send(operation,
                    ResponseOutputTextDone(
                        response_id=operation.response_id,
                        item_id=item_id,
                        text=completed_text,
                        voice=voice,
                    )
                )
                operation.output_item_count += 1
                item_id, completed_text = None, ""

        iterator = operation.output_iterator
        assert iterator is not None
        try:
            async for chunk in iterator:
                self._ensure_writable(operation)
                output_chunks += 1
                if output_chunks > MAX_OUTPUT_CHUNKS:
                    raise ValueError("Response exceeds its chunk budget")
                if isinstance(chunk, Mapping):
                    # SDK input objects are deeply frozen; preserve nested JSON values.
                    data_bytes += len(
                        json.dumps(chunk, default=dict, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":"))
                        .encode("utf-8")
                    )
                    if data_bytes > MAX_DATA_BYTES:
                        raise ValueError("Application data exceeds its byte budget")
                    # A data item cannot interrupt an unfinished text item.
                    await finish_text()
                    await self._send(operation,
                        ResponseOutputDataDone(
                            response_id=operation.response_id,
                            item_id=new_item_id(),
                            data=chunk,
                        )
                    )
                    operation.output_item_count += 1
                    await asyncio.sleep(0)
                    continue
                if not isinstance(chunk, str):
                    raise ValueError("Expected a text chunk or JSON object")
                if not chunk:
                    await asyncio.sleep(0)
                    continue
                output_bytes += len(chunk.encode("utf-8"))
                if output_bytes > MAX_OUTPUT_BYTES:
                    raise ValueError("Response text exceeds its byte budget")
                if item_id is None:
                    item_id = new_item_id()
                completed_text += chunk
                if streaming:
                    await self._send(operation,
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
            await self._close_output(operation)
        await finish_text()
        if operation.output_item_count == 0:
            raise ValueError("Response ended without output")
        await self._send(operation,ResponseDone(response_id=operation.response_id))
        operation.terminal_sent = True
        operation.release_capacity()
        if operation.telemetry is not None:
            operation.telemetry.record_response_done_sent()

    @staticmethod
    async def _fixed_chunks(text: OutputChunk) -> AsyncIterable[OutputChunk]:
        yield text

    async def _run_self_cancel(self, operation: ResponseOperation, text: str) -> None:
        try:
            await self._await_resolution(operation)
            await operation.state.generation_gate.acquire()
            operation.generation_acquired = True
            self._ensure_writable(operation)
            item_id = new_item_id()
            with operation.turn.activate():
                await self._send(operation,
                    ResponseCreated(
                        response_id=operation.response_id,
                        in_reply_to=operation.input_ids,
                    )
                )
                operation.response_started = True
                await self._finish_resolution(operation)
                if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                    raise ValueError("Response text exceeds its output budget")
                await self._send(operation,
                    ResponseOutputTextDelta(
                        response_id=operation.response_id,
                        item_id=item_id,
                        delta=text,
                    )
                )
                await self._send(operation,
                    ResponseCancel(
                        response_id=operation.response_id,
                        reason="sample_self_correction",
                    )
                )
            assert operation.terminal_event is not None
            await operation.terminal_event.wait()
        except asyncio.CancelledError as error:
            if operation.cancellation_requested or not operation.state.active:
                raise
            if operation.telemetry is not None:
                operation.telemetry.record_failure(error)
            await self._report_failure(operation)
        except Exception as error:
            logger.warning("Self-cancelling response failed; error_type=%s", type(error).__name__)
            await self._report_failure(operation)

    def _task_done(
        self,
        state: SessionState,
        operation: ResponseOperation,
        task: asyncio.Task[None],
    ) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.warning("Response task failed; error_type=%s", type(error).__name__)
        self._finalize(state, operation, OperationOutcome.ABANDONED)

    @staticmethod
    def _finalize(
        state: SessionState,
        operation: ResponseOperation,
        fallback: OperationOutcome,
    ) -> None:
        try:
            operation.complete(fallback)
        except Exception as error:
            logger.warning("Response telemetry failed; error_type=%s", type(error).__name__)
        finally:
            state.responses.pop(operation.response_id, None)
            for input_id in operation.input_ids:
                if state.input_responses.get(input_id) == operation.response_id:
                    state.input_responses.pop(input_id, None)

    @staticmethod
    def _clear_state(state: SessionState) -> None:
        state.heard_text_by_response.clear()
        state.seen_inputs.clear()

    async def _report_failure(self, operation: ResponseOperation) -> None:
        if (
            operation.cancellation_requested or operation.terminal_sent
            or not operation.state.active
        ):
            return
        if not operation.response_started:
            operation.select_outcome(OperationOutcome.ERROR)
            return
        try:
            await self._send(operation, AgentError(
                code="generation_failed",
                message="The response could not be generated.",
                response_id=operation.response_id,
            ))
            operation.terminal_sent = True
            operation.select_outcome(OperationOutcome.ERROR)
        except (Exception, asyncio.CancelledError) as error:
            logger.debug("Could not report response failure; error_type=%s", type(error).__name__)
