# Copyright (c) Microsoft. All rights reserved.

"""Bound output before emission; reject empty answers without breaking the next turn."""

import asyncio
import time

import pytest
from test_voice_runtime import RecordingSession

from adapter.response_coordinator import ResponseCoordinator
from adapter.state import SessionState

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
    max_units = 8000
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


async def test_adapter_still_accepts_eight_thousand_small_text_chunks():
    frames, consumed = await run_source(["x"] * 8000)
    assert len(consumed) == 8000
    assert frames[-1].type == "response.done"
    assert not any(frame.type == "error" for frame in frames)


async def test_json_only_output_is_not_empty():
    frames, _ = await run_source(["", {"ok": True}, ""])
    assert [frame.type for frame in frames] == [
        "response.created", "response.output_data.done", "response.done",
    ]
