# Copyright (c) Microsoft. All rights reserved.

"""CE delivery reservations without changing the original Router/Worker store."""

from task_store import Task, TaskStatus, TaskStore


class ConversationTaskStore(TaskStore):
    """Reserve results per response; commit only after successful wire completion."""

    def __init__(self) -> None:
        super().__init__()
        self._delivery_owners: dict[str, str] = {}

    def reserve_completed(self, response_id: str) -> list[Task]:
        return [task for task in self.completed_tasks() if self.reserve_result(response_id, task)]

    def reserve_result(self, response_id: str, task: Task) -> bool:
        # This synchronous claim prevents overlapping waiters from streaming the same result.
        if task.status is not TaskStatus.COMPLETED or task.task_id in self._delivery_owners:
            return False
        self._delivery_owners[task.task_id] = response_id
        return True

    def commit_delivery(self, response_id: str, sent_text: str) -> None:
        for task_id, owner in tuple(self._delivery_owners.items()):
            if owner != response_id:
                continue
            task = self.get(task_id)
            # Merely giving a result to the Router, or emitting an acknowledgment, is not delivery.
            if (task is not None and task.status is TaskStatus.COMPLETED
                    and task.result and task.result in sent_text):
                task.status = TaskStatus.DELIVERED
            self._delivery_owners.pop(task_id)

    def release_delivery(self, response_id: str) -> None:
        for task_id, owner in tuple(self._delivery_owners.items()):
            if owner == response_id:
                self._delivery_owners.pop(task_id)
