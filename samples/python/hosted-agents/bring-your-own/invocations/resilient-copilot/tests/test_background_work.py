import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


SRC = Path(__file__).resolve().parents[1] / "src" / "resilient-copilot"
sys.path.insert(0, str(SRC))

from copilot.session_events import SessionEvent, SessionEventType

import copilot_background
from copilot_session import CopilotHarness, CopilotSessionError


def _event(kind, *, agent_id=None, **data):
    return SimpleNamespace(type=kind, agent_id=agent_id, data=SimpleNamespace(**data))


def _child_event(kind):
    return SessionEvent.from_dict(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "timestamp": "2026-11-22T09:00:00Z",
            "parentId": None,
            "type": kind,
            "data": (
                {"errorType": "subagent", "message": "child failed"}
                if kind == "session.error"
                else {}
            ),
            "agentId": "child",
        }
    )


class _Tasks:
    def __init__(self):
        self.items = []
        self.fail = False
        self.listed = asyncio.Event()

    async def refresh(self):
        if self.fail:
            raise RuntimeError("temporarily unavailable")

    async def list(self):
        self.listed.set()
        return SimpleNamespace(tasks=list(self.items))


def _harness_with_tasks():
    harness = CopilotHarness()
    tasks = _Tasks()
    harness.session = SimpleNamespace(
        rpc=SimpleNamespace(tasks=tasks), abort=AsyncMock()
    )
    return harness, tasks


async def _collect(events, sink):
    async for event in events:
        sink.append(event)


class BackgroundWorkTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_inventory_blocks_completion_and_survives_refresh_failure(self):
        work = copilot_background.BackgroundWork()
        harness, tasks = _harness_with_tasks()
        tasks.items = [{"id": "shell", "type": "shell", "status": "running"}]
        work.observe(_event(SessionEventType.SESSION_IDLE))
        await work.refresh(harness.session)
        self.assertFalse(work.completed())
        tasks.fail = True
        await work.refresh(harness.session)
        self.assertEqual({"shell"}, work.running)
        self.assertFalse(work.completed())
        tasks.fail = False
        tasks.items = []
        await work.refresh(harness.session)
        with patch.object(copilot_background, "IDLE_GRACE_SECONDS", 0):
            self.assertTrue(work.completed())

    async def test_child_idle_does_not_mark_parent_idle(self):
        work = copilot_background.BackgroundWork()
        work.observe(_event(SessionEventType.SUBAGENT_STARTED, tool_call_id="call"))
        work.observe(_child_event("session.idle"))
        self.assertFalse(work.session_idle)
        self.assertEqual({"call"}, work.subagents)

    async def test_short_lived_task_notification_keeps_idle_grace(self):
        work = copilot_background.BackgroundWork()
        harness, _tasks = _harness_with_tasks()
        work.observe(_event(SessionEventType.SESSION_BACKGROUND_TASKS_CHANGED))
        work.observe(_event(SessionEventType.SESSION_IDLE))
        await work.refresh(harness.session)
        self.assertFalse(work.completed())
        self.assertIsNotNone(work.poll_delay())


class HarnessDrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_idle_and_error_do_not_end_the_turn(self):
        harness = CopilotHarness()
        child_idle = _child_event("session.idle")
        child_error = _child_event("session.error")
        main_idle = _event(SessionEventType.SESSION_IDLE)
        for event in (child_idle, child_error, main_idle):
            harness._on_event(event)
        received = []
        await asyncio.wait_for(_collect(harness.events(), received), 2)
        self.assertEqual([child_idle, child_error, main_idle], received)

    async def test_main_session_error_still_terminates(self):
        harness = CopilotHarness()
        harness._on_event(_event(SessionEventType.SESSION_ERROR, message="failed"))
        with self.assertRaises(CopilotSessionError):
            await asyncio.wait_for(_collect(harness.events(), []), 2)

    async def test_detached_shell_keeps_turn_alive_until_inventory_drains(self):
        harness, tasks = _harness_with_tasks()
        tasks.items = [{"id": "shell", "type": "shell", "status": "running"}]
        received = []
        with patch.object(copilot_background, "POLL_SECONDS", 0.05), patch.object(
            copilot_background, "IDLE_GRACE_SECONDS", 0
        ):
            draining = asyncio.create_task(_collect(harness.events(), received))
            idle = _event(SessionEventType.SESSION_IDLE)
            harness._on_event(idle)
            await asyncio.wait_for(tasks.listed.wait(), 2)
            await asyncio.sleep(0.2)
            self.assertFalse(draining.done())
            tasks.items = [{"id": "shell", "type": "shell", "status": "completed"}]
            await asyncio.wait_for(draining, 2)
        self.assertEqual([idle], received)

    async def test_subagent_completion_and_followup_turn_drain_within_grace(self):
        harness, tasks = _harness_with_tasks()
        started = _event(SessionEventType.SUBAGENT_STARTED, tool_call_id="call")
        first_idle = _event(SessionEventType.SESSION_IDLE)
        completed = _event(SessionEventType.SUBAGENT_COMPLETED, tool_call_id="call")
        notice = _event(SessionEventType.SYSTEM_NOTIFICATION)
        followup = _event(SessionEventType.ASSISTANT_MESSAGE, content="done")
        final_idle = _event(SessionEventType.SESSION_IDLE)
        received = []
        with patch.object(copilot_background, "IDLE_GRACE_SECONDS", 0.3):
            harness._on_event(started)
            harness._on_event(first_idle)
            draining = asyncio.create_task(_collect(harness.events(), received))
            await asyncio.sleep(0.1)
            self.assertFalse(draining.done())
            for event in (completed, notice, followup, final_idle):
                harness._on_event(event)
            await asyncio.wait_for(draining, 2)
        self.assertEqual(
            [started, first_idle, completed, notice, followup, final_idle], received
        )

    async def test_send_after_consumed_idle_waits_for_the_new_idle(self):
        harness = CopilotHarness()
        harness.session = SimpleNamespace(send=AsyncMock(return_value="message-id"))
        first_idle = _event(SessionEventType.SESSION_IDLE)
        steer = SimpleNamespace(kind="steer")
        harness._on_event(first_idle)
        harness._queue.put_nowait(steer)
        events = harness.events()
        self.assertIs(await anext(events), first_idle)
        self.assertIs(await anext(events), steer)
        await harness.send("steer", mode="immediate", causal_idle=True)
        waiting = asyncio.create_task(anext(events))
        await asyncio.sleep(0.05)
        self.assertFalse(waiting.done())
        second_idle = _event(SessionEventType.SESSION_IDLE)
        harness._on_event(second_idle)
        self.assertIs(await asyncio.wait_for(waiting, 2), second_idle)

    async def test_abort_stops_draining_background_work(self):
        harness, tasks = _harness_with_tasks()
        tasks.items = [{"id": "shell", "type": "shell", "status": "running"}]
        received = []
        draining = asyncio.create_task(_collect(harness.events(), received))
        harness._on_event(_event(SessionEventType.SESSION_IDLE))
        await asyncio.wait_for(tasks.listed.wait(), 2)
        await harness.abort()
        await asyncio.wait_for(draining, 2)
        harness.session.abort.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
