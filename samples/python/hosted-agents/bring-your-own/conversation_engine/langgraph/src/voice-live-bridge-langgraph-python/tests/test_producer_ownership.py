# Copyright (c) Microsoft. All rights reserved.

"""Accepted producers remain owned through startup, cancellation and finalization."""

import asyncio

import pytest

from response_coordinator import ResponseCoordinator
from state import OperationOutcome, SessionState


class Session:
    def __init__(self, mode):
        self.mode = mode
        self.created = asyncio.Event()
        self.sent = []

    async def send(self, event):
        if event.type == "response.created":
            self.created.set()
            if self.mode == "created_failure":
                raise RuntimeError("private synthetic send failure")
            if self.mode == "created_block":
                await asyncio.Future()
        self.sent.append(event)


class Producer:
    def __init__(self, *, gate=None, fail_close=False):
        self.gate = gate
        self.fail_close = fail_close
        self.close_started = asyncio.Event()
        self.closed = False
        self.close_calls = 0
        self.iterations = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.iterations += 1
        if self.iterations > 1:
            raise StopAsyncIteration
        return "output"

    async def aclose(self):
        self.close_calls += 1
        self.close_started.set()
        if self.gate is not None:
            await self.gate.wait()
        self.closed = True
        if self.fail_close:
            raise RuntimeError("private synthetic cleanup failure")


def active_state():
    state = SessionState()
    assert state.try_begin_start()
    state.activate()
    return state


@pytest.mark.parametrize("pre_start", [False, True])
async def test_cancelled_queued_producer_closes_before_blocked_predecessor(pre_start):
    coordinator, state = ResponseCoordinator(), active_state()
    blocked, release = asyncio.Event(), asyncio.Event()
    sent = []

    class BlockedSession:
        async def send(self, message):
            if message.type == "response.created" and message.response_id == "r_first":
                blocked.set()
                await release.wait()
            sent.append(message)

    session, source = BlockedSession(), Producer()
    coordinator.start_response(session, state, "in_first", Producer(), response_id="r_first")
    await asyncio.wait_for(blocked.wait(), 2)
    coordinator.start_response(session, state, "in_cancel", source, response_id="r_cancel")
    cancelled = state.responses["r_cancel"]
    if not pre_start:
        await asyncio.sleep(0)  # Enter the wait on the first resolution.
    coordinator.response_timeout(state, None, ["in_cancel"])
    try:
        await asyncio.wait_for(source.close_started.wait(), 2)
        await asyncio.wait_for(asyncio.gather(cancelled.task, return_exceptions=True), 2)
        await asyncio.sleep(0)
        assert source.closed and source.close_calls == 1 and source.iterations == 0
        assert cancelled.task.done()
        # Retain bounded ordering bookkeeping, but not live producer cleanup.
        assert state.active_response_count == 2
        assert state.responses["r_cancel"] is cancelled
        coordinator.start_response(session, state, "in_third", Producer(), response_id="r_third")
        third = state.responses["r_third"]
        await asyncio.sleep(0)
        assert not third.task.done()
        assert sent == []  # Cancelling the middle entry cannot release its successor early.
        release.set()
        await asyncio.wait_for(third.task, 2)
        assert [message.response_id for message in sent
                if message.type == "response.created"] == ["r_first", "r_third"]
        await asyncio.sleep(0)
        assert state.active_response_count == 0
    finally:
        release.set()
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)



@pytest.mark.parametrize("mode", ["pre_start", "created_block", "created_failure"])
async def test_every_exit_before_iteration_closes_accepted_producer(mode):
    coordinator, state = ResponseCoordinator(), active_state()
    session, source = Session(mode), Producer()
    assert coordinator.start_response(session, state, "in_owned", source)
    operation = next(iter(state.responses.values()))
    if mode != "pre_start":
        await asyncio.wait_for(session.created.wait(), 2)
    if mode != "created_failure":
        coordinator.cancel_response(state, operation.response_id, OperationOutcome.TIMEOUT)
    await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), 2)
    await asyncio.sleep(0)
    assert source.closed and source.close_calls == 1
    assert source.iterations == 0
    assert not state.responses and not state.input_responses
    assert not any(event.type == "response.done" for event in session.sent)
    if mode == "created_failure":
        assert session.sent[-1].type == "error"
        assert "private" not in session.sent[-1].message


@pytest.mark.parametrize("pre_start", [False, True])
async def test_cancellation_retains_capacity_until_asynchronous_close_finishes(pre_start):
    coordinator, state, session = ResponseCoordinator(), active_state(), Session("normal")
    gate = asyncio.Event()
    source = Producer(gate=gate)
    assert coordinator.start_response(session, state, "in_owned", source)
    operation = next(iter(state.responses.values()))
    try:
        if pre_start:
            coordinator.cancel_response(state, operation.response_id, OperationOutcome.TIMEOUT)
        await asyncio.wait_for(source.close_started.wait(), 2)
        if not pre_start:
            coordinator.cancel_response(state, operation.response_id, OperationOutcome.TIMEOUT)
        await asyncio.sleep(0)
        assert not operation.task.done()
        assert state.responses[operation.response_id] is operation
        assert state.active_response_count == 1
        assert not source.closed
        assert not any(event.type == "response.done" for event in session.sent)
    finally:
        gate.set()
        await asyncio.wait_for(asyncio.gather(operation.task, return_exceptions=True), 2)
        await coordinator.terminate_state(state, OperationOutcome.END_CALL)
    assert source.closed and source.close_calls == 1


async def test_producer_close_failure_is_not_reported_as_success():
    coordinator, state, session = ResponseCoordinator(), active_state(), Session("normal")
    source = Producer(fail_close=True)
    assert coordinator.start_response(session, state, "in_owned", source)
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(operation.task, 2)
    await asyncio.sleep(0)
    assert source.close_calls == 1
    assert session.sent[-1].type == "error"
    assert not any(event.type == "response.done" for event in session.sent)
    assert not state.responses
