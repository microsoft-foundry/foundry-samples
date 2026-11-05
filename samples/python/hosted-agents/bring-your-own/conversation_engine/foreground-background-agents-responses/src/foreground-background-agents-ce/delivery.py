# Copyright (c) Microsoft. All rights reserved.

"""CE delivery reservations without changing the original Router/Worker store."""

from task_store import Task, TaskStatus, TaskStore


class ConversationTaskStore(TaskStore):
    """Reserve results per response; commit only after successful wire completion."""

    def __init__(self) -> None:
        super().__init__()
        self._delivery_owners: dict[str, str] = {}
        self._emitted_results: dict[str, set[str]] = {}

    def reserve_completed(self, response_id: str) -> list[Task]:
        return [task for task in self.completed_tasks() if self.reserve_result(response_id, task)]

    def reserve_result(self, response_id: str, task: Task) -> bool:
        # This synchronous claim prevents overlapping waiters from streaming the same result.
        if task.status is not TaskStatus.COMPLETED:
            return False
        if task.task_id in self._delivery_owners:
            return self._delivery_owners[task.task_id] == response_id
        self._delivery_owners[task.task_id] = response_id
        return True

    def record_emitted(self, response_id: str, task_ids: list[str]) -> None:
        """Associate completed result emissions, including paraphrases, with task IDs."""
        if any(self._delivery_owners.get(task_id) != response_id for task_id in task_ids):
            raise ValueError("Result emission requires an owned reservation")
        if task_ids:
            self._emitted_results.setdefault(response_id, set()).update(task_ids)

    def result_emitted(self, response_id: str, task_id: str) -> bool:
        return task_id in self._emitted_results.get(response_id, set())

    def commit_delivery(self, response_id: str) -> None:
        emitted = self._emitted_results.get(response_id, set())
        for task_id, owner in tuple(self._delivery_owners.items()):
            if owner != response_id:
                continue
            task = self.get(task_id)
            # Text equality cannot identify a paraphrase or distinguish "1" from "10".
            if (task is not None and task.status is TaskStatus.COMPLETED
                    and task_id in emitted):
                task.status = TaskStatus.DELIVERED
        self.release_delivery(response_id)

    def release_delivery(self, response_id: str) -> None:
        self._emitted_results.pop(response_id, None)
        for task_id, owner in tuple(self._delivery_owners.items()):
            if owner == response_id:
                self._delivery_owners.pop(task_id)
