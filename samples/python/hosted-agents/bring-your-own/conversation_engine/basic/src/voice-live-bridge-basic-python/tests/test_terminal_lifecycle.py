# Copyright (c) Microsoft. All rights reserved.

"""Response terminal ownership and ordinary cooperative cleanup."""

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from test_voice_runtime import RecordingSession

from response_coordinator import ResponseCoordinator
from state import OperationOutcome, SessionState


def active_state() -> SessionState:
    state = SessionState()
    state.try_begin_start()
    state.activate()
    return state


class OwnedSource:
    def __init__(self) -> None:
        self.closed = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def aclose(self):
        self.closed += 1


@pytest.mark.parametrize("when", ["before_start", "created_send"])
@pytest.mark.parametrize("setup_error", [None, RuntimeError, asyncio.CancelledError])
async def test_accepted_source_is_closed_even_before_iteration(when, setup_error) -> None:
    coordinator = ResponseCoordinator()
    state = active_state()

    class Session(RecordingSession):
        async def send(self, message):
            if when == "created_send" and message.type == "response.created":
                raise RuntimeError("controlled transport failure")
            await super().send(message)

    session = Session()

    class Source(OwnedSource):
        def __aiter__(self):
            if setup_error is not None:
                raise setup_error("controlled setup failure")
            return self

    source = Source()
    coordinator.send_echo(session, state, "in_owned", source, time.monotonic())
    operation = next(iter(state.responses.values()))
    if when == "before_start":
        coordinator.cancel_response(state, operation.response_id, OperationOutcome.TIMEOUT)
    await asyncio.gather(operation.task, return_exceptions=True)
    await asyncio.sleep(0)
    assert source.closed == 1
    assert not state.responses and not state.input_responses
    assert not any(message.type == "response.done" for message in session.sent)


@pytest.mark.parametrize("cancel", [False, True])
async def test_producer_iteration_and_close_keep_the_same_context(cancel: bool) -> None:
    from contextvars import ContextVar

    scope = ContextVar("producer_scope", default="outside")
    waiting = asyncio.Event()
    reset = False

    async def source() -> AsyncIterator[str]:
        nonlocal reset
        token = scope.set("inside")
        try:
            yield "first"
            assert scope.get() == "inside"
            waiting.set()
            if cancel:
                await asyncio.Future()
        finally:
            scope.reset(token)
            reset = True

    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    coordinator.send_echo(session, state, "in_scope", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(waiting.wait(), 2)
    if cancel:
        coordinator.cancel_response(state, operation.response_id, OperationOutcome.CANCELLED)
    await asyncio.gather(operation.task, return_exceptions=True)
    assert reset and scope.get() == "outside"
    assert bool([message for message in session.sent if message.type == "response.done"]) != cancel


async def test_runtime_session_end_and_cancelled_close_retain_cleanup() -> None:
    from types import SimpleNamespace

    from test_voice_runtime import create_app

    runtime = create_app(configure_observability=None).state.voice_runtime
    session = RecordingSession()
    await runtime.on_session_start(session, SimpleNamespace(protocol_version="1.0"))
    state = runtime._store.active(session)
    assert state is not None
    waiting, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def source() -> AsyncIterator[str]:
        try:
            yield "first"
            waiting.set()
            await asyncio.Future()
        finally:
            closing.set()
            await release.wait()

    runtime._coordinator.send_echo(session, state, "in_runtime", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(waiting.wait(), 2)
    await asyncio.wait_for(runtime.on_session_end(session, None), 2)
    await asyncio.wait_for(closing.wait(), 2)
    first_join = asyncio.create_task(runtime.close())
    second_join = None
    try:
        await asyncio.sleep(0)
        first_join.cancel()
        await asyncio.gather(first_join, return_exceptions=True)
        assert not operation.task.done()
        second_join = asyncio.create_task(runtime.close())
        await asyncio.sleep(0)
        assert not second_join.done()
        assert runtime._coordinator._detached_tasks
    finally:
        release.set()
        if second_join is not None:
            await asyncio.wait_for(second_join, 2)
    assert not state.responses and not runtime._coordinator._detached_tasks
    assert not any(message.type == "response.done" for message in session.sent)


@pytest.mark.parametrize("own_cancel", [False, True])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_iterator_setup_failure_is_ordered_and_does_not_break_next_input(
    own_cancel: bool, close_fails: bool,
) -> None:
    class FailingSource(OwnedSource):
        def __aiter__(self):
            if own_cancel:
                raise asyncio.CancelledError()
            raise RuntimeError("controlled iterator setup failure")

        async def aclose(self):
            await super().aclose()
            if close_fails:
                raise ValueError("secondary close failure")

    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    source = FailingSource()
    assert coordinator.send_echo(session, state, "in_setup", source, time.monotonic())
    failed = next(iter(state.responses.values()))
    assert coordinator.start_response(session, state, "in_followup", "retry", streaming=False)
    tasks = [operation.task for operation in state.responses.values()]
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0)
    assert [message.type for message in session.sent] == [
        "response.created", "error", "response.created",
        "response.output_text.done", "response.done",
    ]
    assert session.sent[0].in_reply_to == ("in_setup",)
    assert session.sent[2].in_reply_to == ("in_followup",)
    assert failed.outcome is OperationOutcome.ERROR
    assert source.closed == 1
    assert not state.responses and not state.input_responses
    await coordinator.wait_for_detached_tasks()
    assert not coordinator._detached_tasks


@pytest.mark.parametrize("own_cancel", [False, True])
async def test_setup_failure_retains_source_until_async_close_and_shutdown_settle(own_cancel):
    closing, release = asyncio.Event(), asyncio.Event()

    class Source(OwnedSource):
        def __aiter__(self):
            raise asyncio.CancelledError() if own_cancel else RuntimeError("setup failed")

        async def aclose(self):
            closing.set()
            await release.wait()
            await super().aclose()

    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    source = Source()
    coordinator.send_echo(session, state, "in_setup", source, time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(closing.wait(), 2)
    shutdown = asyncio.create_task(coordinator.terminate_state(state, OperationOutcome.ABANDONED))
    try:
        await asyncio.sleep(0)
        assert state.responses.get(operation.response_id) is operation
        assert not operation.task.done() and source.closed == 0
        shutdown.cancel()
        await asyncio.gather(shutdown, return_exceptions=True)
        assert not operation.task.done()
    finally:
        release.set()
        await asyncio.wait_for(coordinator.wait_for_detached_tasks(), 2)
    assert source.closed == 1
    assert not state.responses and not state.input_responses
    assert not coordinator._detached_tasks
    assert [frame.type for frame in session.sent] == ["response.created", "error"]


async def test_successful_setup_transfers_close_ownership_to_returned_iterator():
    source_closes = 0
    iterator_closes = 0

    class Source:
        def __aiter__(self):
            return chunks()

        async def aclose(self):
            nonlocal source_closes
            source_closes += 1

    async def chunks():
        nonlocal iterator_closes
        try:
            yield "answer"
        finally:
            iterator_closes += 1

    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    coordinator.send_echo(session, state, "in_ok", Source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(operation.task, 2)
    await asyncio.sleep(0)
    assert source_closes == 0 and iterator_closes == 1
    assert not state.responses and session.sent[-1].type == "response.done"


@pytest.mark.parametrize("before_start", [False, True])
async def test_cancelled_queued_close_retains_capacity_without_blocking_successor(before_start):
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    closing, release = asyncio.Event(), asyncio.Event()
    closed = False

    class QueuedSource(OwnedSource):
        async def aclose(self):
            nonlocal closed
            closing.set()
            await release.wait()
            closed = True

    # Model an earlier generation whose input decision has already been sent.
    await state.generation_gate.acquire()
    coordinator.send_echo(session, state, "in_cancelled", QueuedSource(), time.monotonic())
    old = next(iter(state.responses.values()))
    if not before_start:
        await asyncio.sleep(0)
    coordinator.response_timeout(state, None, ("in_cancelled",))
    await asyncio.wait_for(closing.wait(), 2)
    state.generation_gate.release()
    coordinator.start_response(session, state, "in_next", "next", streaming=False)
    next_operation = next(value for value in state.responses.values() if value is not old)
    try:
        # Shield the owned task: a failed assertion must not cancel the regression subject.
        await asyncio.wait_for(asyncio.shield(next_operation.task), 0.2)
        await asyncio.sleep(0)
        assert not closed
        assert state.responses.get(old.response_id) is old
        assert state.active_response_count == 1
        assert state.input_responses.get("in_cancelled") == old.response_id
        assert not any(
            getattr(frame, "response_id", None) == old.response_id for frame in session.sent
        )
        assert session.sent[-1].type == "response.done"
    finally:
        release.set()
        await asyncio.gather(old.task, next_operation.task, return_exceptions=True)
        await asyncio.sleep(0)
    assert closed and not state.responses and not state.input_responses
    assert coordinator.start_response(session, state, "in_followup", "followup", streaming=False)
    followup = next(iter(state.responses.values()))
    await asyncio.wait_for(followup.task, 2)
    assert session.sent[-1].type == "response.done"


async def test_producer_cancellation_is_failure_not_protocol_cancellation() -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()

    async def source() -> AsyncIterator[str]:
        if False:
            yield ""
        raise asyncio.CancelledError()

    coordinator.send_echo(session, state, "in_failure", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.gather(operation.task, return_exceptions=True)
    assert [message.type for message in session.sent] == ["response.created", "error"]
    assert session.sent[-1].response_id == operation.response_id
    assert operation.outcome is OperationOutcome.ERROR
    assert not state.responses


@pytest.mark.parametrize("behavior", ["cleanup_error", "swallow_cancel"])
async def test_cancelled_response_cannot_send_after_replacement(behavior: str) -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    waiting = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()

    async def first() -> AsyncIterator[str]:
        try:
            yield "first"
            waiting.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                if behavior == "swallow_cancel":
                    yield "STALE"
                else:
                    raise
        finally:
            closing.set()
            await release.wait()
            if behavior == "cleanup_error":
                raise RuntimeError("controlled cleanup failure")

    async def second() -> AsyncIterator[str]:
        yield "second"

    coordinator.send_echo(session, state, "in_first", first(), time.monotonic())
    old = next(iter(state.responses.values()))
    try:
        await asyncio.wait_for(waiting.wait(), 2)
        coordinator.cancel_response(state, old.response_id, OperationOutcome.CANCELLED)
        await asyncio.wait_for(closing.wait(), 2)
        assert old.response_id in state.responses
        coordinator.send_echo(session, state, "in_second", second(), time.monotonic())
        replacement = next(value for value in state.responses.values() if value is not old)
        await asyncio.wait_for(replacement.task, 2)
    finally:
        release.set()
        await asyncio.gather(old.task, return_exceptions=True)
    old_frames = [message for message in session.sent if
                  getattr(message, "response_id", None) == old.response_id]
    assert [message.type for message in old_frames] == [
        "response.created", "response.output_text.delta",
    ]
    assert old.outcome is OperationOutcome.CANCELLED
    assert not state.responses and not state.input_responses


async def test_cancelled_drain_join_retains_worker_for_later_shutdown() -> None:
    coordinator = ResponseCoordinator()
    state = active_state()
    session = RecordingSession()
    waiting = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()

    async def source() -> AsyncIterator[str]:
        try:
            yield "first"
            waiting.set()
            await asyncio.Future()
        finally:
            closing.set()
            await release.wait()

    coordinator.send_echo(session, state, "in_drain", source(), time.monotonic())
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(waiting.wait(), 2)
    joining = asyncio.create_task(coordinator.terminate_state(state, OperationOutcome.END_CALL))
    try:
        await asyncio.wait_for(closing.wait(), 2)
        joining.cancel()
        await asyncio.gather(joining, return_exceptions=True)
        assert not operation.task.done()
        shutdown = asyncio.create_task(coordinator.wait_for_detached_tasks())
        await asyncio.sleep(0)
        assert not shutdown.done()
        release.set()
        await asyncio.wait_for(shutdown, 2)
    finally:
        release.set()
        await asyncio.gather(operation.task, joining, return_exceptions=True)
    assert not state.responses and not state.input_responses
