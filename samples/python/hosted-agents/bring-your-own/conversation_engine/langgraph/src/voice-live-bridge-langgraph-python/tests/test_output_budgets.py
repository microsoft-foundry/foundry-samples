# Copyright (c) Microsoft. All rights reserved.

"""Bound output before emission; reject empty answers without breaking the next turn."""

import asyncio
import time

import pytest
from test_voice_runtime import RecordingSession

from response_coordinator import ResponseCoordinator
from state import SessionState

MAX_BYTES = 512 * 1024
MAX_CHUNKS = 4096


async def run_source(chunks, *, streaming=True):
    coordinator = ResponseCoordinator()
    state = SessionState()
    state.try_begin_start()
    state.activate()
    session = RecordingSession()
    closed = []
    consumed = []

    async def source():
        try:
            for chunk in chunks:
                consumed.append(chunk)
                yield chunk
        finally:
            closed.append(True)

    coordinator.start_response(
        session, state, "in_budget", source(), time.monotonic(), streaming=streaming,
    )
    operation = next(iter(state.responses.values()))
    await asyncio.gather(operation.task, return_exceptions=True)
    await asyncio.sleep(0)
    assert closed == [True]
    assert not state.responses and not state.input_responses
    assert state.active_response_count == 0
    original = list(session.sent)
    # Both error and success must leave the connection usable for a fresh response.
    assert coordinator.start_response(session, state, "in_retry", "retry", streaming=False)
    retry = next(iter(state.responses.values()))
    await asyncio.gather(retry.task, return_exceptions=True)
    await asyncio.sleep(0)
    assert session.sent[-1].type == "response.done"
    assert not state.responses and not state.input_responses
    return original, consumed


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("chunks", [[], [""], ["", ""]])
async def test_empty_output_is_failure(chunks, streaming):
    frames, _ = await run_source(chunks, streaming=streaming)
    assert [frame.type for frame in frames] == ["response.created", "error"]
    assert frames[-1].code == "generation_failed"

@pytest.mark.parametrize("unit", ["x", "💡"])
@pytest.mark.parametrize("over", [False, True])
async def test_self_cancel_output_uses_the_same_text_budget(unit, over):
    coordinator = ResponseCoordinator()
    state = SessionState()
    state.try_begin_start()
    state.activate()
    ready = asyncio.Event()

    class TerminalSession(RecordingSession):
        async def send(self, message):
            await super().send(message)
            if message.type in {"error", "response.cancel"}:
                ready.set()

    session = TerminalSession()
    max_units = MAX_BYTES // len(unit.encode("utf-8"))
    text = unit * (max_units + int(over))
    assert coordinator.start_self_cancel(
        session, state, "in_self", text, time.monotonic(),
    )
    operation = next(iter(state.responses.values()))
    await asyncio.wait_for(ready.wait(), 2)
    if any(frame.type == "response.cancel" for frame in session.sent):
        coordinator.response_cancelled(state, operation.response_id, "")
    await asyncio.gather(operation.task, return_exceptions=True)
    await asyncio.sleep(0)
    deltas = [frame.delta for frame in session.sent if frame.type == "response.output_text.delta"]
    assert deltas == ([] if over else [text])
    assert sum(frame.type == "error" for frame in session.sent) == int(over)
    assert not any(frame.type == "response.done" for frame in session.sent)
    assert not state.responses and not state.input_responses
    assert coordinator.start_response(session, state, "in_next", "retry", streaming=False)
    retry = next(iter(state.responses.values()))
    await asyncio.gather(retry.task, return_exceptions=True)
    assert session.sent[-1].type == "response.done"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("text", ["answer", " \t\n"])
async def test_empty_chunks_do_not_create_output_but_whitespace_is_preserved(text, streaming):
    frames, _ = await run_source(["", text, ""], streaming=streaming)
    assert [frame.text for frame in frames if frame.type == "response.output_text.done"] == [text]
    assert [frame.delta for frame in frames if frame.type == "response.output_text.delta"] == (
        [text] if streaming else []
    )
    assert frames[-1].type == "response.done"
    assert not any(frame.type == "error" for frame in frames)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("unit", ["x", "💡"])
@pytest.mark.parametrize("over", [False, True])
async def test_total_utf8_budget_is_checked_before_emission(unit, over, streaming):
    half = unit * (MAX_BYTES // 2 // len(unit.encode("utf-8")))
    chunks = [half, half] + (["!", "NEVER"] if over else [])
    frames, consumed = await run_source(chunks, streaming=streaming)
    sent = "".join(frame.delta for frame in frames if frame.type == "response.output_text.delta")
    assert len(sent.encode("utf-8")) <= MAX_BYTES
    if over:
        assert frames[-1].type == "error"
        assert not any(
            frame.type in {"response.output_text.done", "response.done"} for frame in frames
        )
        assert consumed == chunks[:-1]
    else:
        assert frames[-1].type == "response.done"
        done = next(frame.text for frame in frames if frame.type == "response.output_text.done")
        assert len(done.encode("utf-8")) == MAX_BYTES


async def test_single_oversized_chunk_is_not_forwarded():
    frames, consumed = await run_source(["x" * (MAX_BYTES + 1), "NEVER"])
    assert [frame.type for frame in frames] == ["response.created", "error"]
    assert len(consumed) == 1


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("over", [False, True])
async def test_chunk_count_is_bounded_before_emission(over, streaming):
    count = MAX_CHUNKS + int(over)
    frames, consumed = await run_source(["x"] * count + (["NEVER"] if over else []),
                                        streaming=streaming)
    deltas = [frame for frame in frames if frame.type == "response.output_text.delta"]
    assert len(deltas) == (MAX_CHUNKS if streaming else 0)
    assert len(consumed) == count
    assert frames[-1].type == ("error" if over else "response.done")
    if over:
        assert not any(frame.type == "response.done" for frame in frames)


async def test_empty_chunks_cannot_bypass_chunk_budget():
    frames, consumed = await run_source([""] * (MAX_CHUNKS + 2))
    assert [frame.type for frame in frames] == ["response.created", "error"]
    assert len(consumed) == MAX_CHUNKS + 1


@pytest.mark.parametrize("value", [None, 0, {}])
async def test_empty_nontext_value_is_not_silently_ignored(value):
    frames, consumed = await run_source([value, "NEVER"])
    assert [frame.type for frame in frames] == ["response.created", "error"]
    assert len(consumed) == 1
