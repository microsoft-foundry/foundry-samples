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


class TaskStore:
    """In-memory task registry. One instance shared across the app."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create_task(self, query: str) -> Task:
        task_id = uuid.uuid4().hex[:8]
        task = Task(task_id=task_id, query=query)
        self._tasks[task_id] = task
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
        return [t for t in self._tasks.values()
                if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)]

    def completed_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values()
                if t.status == TaskStatus.COMPLETED]

    def delivered_tasks(self) -> list[Task]:
        """Return tasks that have been delivered to the user (for context recall)."""
        return [t for t in self._tasks.values()
                if t.status == TaskStatus.DELIVERED]

    def collect_completed(self) -> list[Task]:
        """Return all completed tasks and mark them as delivered.

        This ensures each result is delivered to the user exactly once.
        """
        ready = [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]
        for t in ready:
            t.status = TaskStatus.DELIVERED
        return ready

    def cleanup(self):
        """Remove delivered/cancelled/failed tasks older than 5 minutes."""
        import time as _time
        cutoff = _time.time() - 300
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.DELIVERED, TaskStatus.CANCELLED, TaskStatus.FAILED)
            and t.created_at < cutoff
        ]
        for tid in to_remove:
            del self._tasks[tid]

    def _get_latest(self) -> Task | None:
        if not self._tasks:
            return None
        return list(self._tasks.values())[-1]
