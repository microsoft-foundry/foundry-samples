"""Drain must progress when all retained tasks finished before the join."""

import asyncio

import pytest

from adapter.response_coordinator import ResponseCoordinator


@pytest.mark.asyncio
async def test_drain_yields_to_completed_task_release_callback() -> None:
    coordinator = ResponseCoordinator()
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    coordinator._retain_task(task)
    await asyncio.wait_for(coordinator.wait_for_detached_tasks(), 1)
    assert not coordinator._detached_tasks
