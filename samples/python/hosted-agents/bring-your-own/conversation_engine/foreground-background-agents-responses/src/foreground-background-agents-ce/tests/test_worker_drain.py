# Copyright (c) Microsoft. All rights reserved.

"""Coroutine cancellation does not stop synchronous executor operations."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

import worker_agent
from task_store import TaskStatus
from voice_runtime import Conversation, VoiceRuntime


@pytest.mark.parametrize("operation", ["model", "tool"])
@pytest.mark.parametrize("termination", ["close", "session.end", "disconnect", "cancelled_join"])
async def test_session_cleanup_tracks_executor_work_until_it_settles(
    monkeypatch, operation, termination
):
    entered, release, settled = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def blocked():
        entered.set()
        try:
            assert release.wait(5), "test did not release its synchronous operation"
            return "RESULT"
        finally:
            settled.set()

    def model(**_kwargs):
        calls.append(True)
        if operation == "model":
            return SimpleNamespace(output=[], output_text=blocked())
        return SimpleNamespace(output_text="", output=[SimpleNamespace(
            type="function_call", name="search_site_specs", arguments={},
            id="call_1", call_id="call_1",
        )])

    monkeypatch.setattr(worker_agent, "_execute_tool", lambda *_args: blocked())
    runtime = VoiceRuntime(None)
    session = object()
    conversation = Conversation()
    runtime._conversations[session] = conversation
    task = conversation.task_store.create_task("work")
    worker = asyncio.create_task(worker_agent.run_worker(
        task, [], SimpleNamespace(create=model), "test-model"
    ))
    conversation.background_tasks.add(worker)
    worker.add_done_callback(conversation.background_tasks.discard)
    cleanup = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if termination == "disconnect":
            runtime.on_connection_terminating(session)
            cleanup = asyncio.create_task(runtime.close())
        elif termination == "session.end":
            cleanup = asyncio.create_task(runtime.on_session_end(session, None))
        else:
            cleanup = asyncio.create_task(runtime.close())
        await asyncio.sleep(0)
        assert task.cancel_event.is_set()
        assert not cleanup.done()
        assert not settled.is_set()
        assert not worker.done()
        assert worker in runtime._detached_workers
        if termination == "cancelled_join":
            cleanup.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cleanup
            assert not worker.done()
            assert worker in runtime._detached_workers
            cleanup = asyncio.create_task(runtime.close())
        release.set()
        await asyncio.wait_for(cleanup, 2)
        assert settled.is_set()
        assert worker.done() and not worker.cancelled()
        assert task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        assert len(calls) == 1  # Cooperative cancellation does not start another model round.
        assert not runtime._detached_workers
    finally:
        release.set()
        await asyncio.gather(worker, return_exceptions=True)
        if cleanup is not None:
            await asyncio.gather(cleanup, return_exceptions=True)
        await runtime.close()
