"""Task Store — shared state between Router and Worker agents.

Tracks background tasks: their status, current progress, results, and cancellation.
In production, replace the in-memory dict with Redis or Cosmos DB.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    query: str
    status: TaskStatus = TaskStatus.QUEUED
    current_tool: str | None = None
    rounds_completed: int = 0
    result: str | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class TaskStore:
    """In-memory task registry. One instance per physical CE connection."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._latest_task_id: str | None = None

    def create_task(self, query: str) -> Task:
        task_id = uuid.uuid4().hex[:8]
        task = Task(task_id=task_id, query=query)
        self._tasks[task_id] = task
        self._latest_task_id = task_id
        return task

    def get(self, task_id: str) -> Task | None:
        if task_id == "latest":
            return self._get_latest()
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task and task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            task.cancel_event.set()
            return True
        return False

    def active_tasks(self) -> list[Task]:
        return [
            t for t in self._tasks.values() if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
        ]

    def completed_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]

    def delivered_tasks(self) -> list[Task]:
        """Return tasks that have been delivered to the user (for context recall)."""
        return [t for t in self._tasks.values() if t.status == TaskStatus.DELIVERED]

    def terminal_tasks(self) -> list[Task]:
        """Expose sanitized failure/cancellation status to subsequent Router turns."""
        return [
            task
            for task in self._tasks.values()
            if task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]

    def cleanup(self):
        """Retain terminal outcomes for five minutes after Worker completion."""
        import time as _time

        cutoff = _time.time() - 300
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status in (TaskStatus.DELIVERED, TaskStatus.CANCELLED, TaskStatus.FAILED)
            and t.finished_at is not None
            and t.finished_at < cutoff
        ]
        for tid in to_remove:
            del self._tasks[tid]

    def _get_latest(self) -> Task | None:
        # An expired latest reference must not silently return an older task.
        return self._tasks.get(self._latest_task_id)
