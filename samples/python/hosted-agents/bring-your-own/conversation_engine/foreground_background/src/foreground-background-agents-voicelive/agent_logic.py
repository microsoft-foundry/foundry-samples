"""The original Router/Worker workflow, independent of CE wire messages."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from router_agent import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_TOOL_CHOICE,
    ROUTER_TOOLS,
    build_delivered_context,
    build_task_context,
    execute_router_tool,
)
from task_store import Task, TaskStatus, TaskStore
from worker_agent import run_worker

logger = logging.getLogger(__name__)
STATUS_INTERVAL = 5.0
STATUS_TIMEOUT = 1.0
MAX_TASK_CONTEXT_CHARACTERS = 8_000
MAX_MODEL_HISTORY_CHARACTERS = 16_000


@dataclass
class HistoryEntry:
    role: str
    content: str
    response_id: str | None = None


@dataclass
class Conversation:
    """Business state belongs to one physical CE connection, never the app."""

    tasks: TaskStore = field(default_factory=TaskStore)
    history: deque[HistoryEntry] = field(default_factory=lambda: deque(maxlen=20))

    def cancel_workers(self) -> None:
        for task in self.tasks.active_tasks():
            task.cancel_event.set()

    def reconcile(self, response_id: str, heard_text: str, *, allow_append: bool = False) -> None:
        for entry in self.history:
            if entry.response_id == response_id:
                entry.content = heard_text
                return
        if allow_append and heard_text:
            # Only a first in-flight send can be missing without having been evicted.
            self.history.append(HistoryEntry("assistant", heard_text, response_id))


@dataclass
class Turn:
    response_id: str
    delivered_task_ids: set[str] = field(default_factory=set)


def task_message(task: Task) -> str:
    if task.status is TaskStatus.FAILED:
        return "Sorry, the background work failed. Please try again."
    if task.status is TaskStatus.CANCELLED:
        return "The background work was cancelled."
    return task.result or "No result yet."


def text_chunks(text: str) -> list[str]:
    # Keep the original voice-friendly chunk size.
    return [text[index : index + 40] for index in range(0, len(text), 40)]


class ForegroundBackgroundAgent:
    """Own model clients and retained Workers; protocol responses are separate."""

    def __init__(self, chat: Any, responses: Any, model: str) -> None:
        self.chat = chat
        self.responses = responses
        self.model = model
        self.workers: set[asyncio.Task[None]] = set()
        self._clients: list[Any] = []
        self._async_clients: list[Any] = []

    @classmethod
    def from_environment(cls) -> ForegroundBackgroundAgent:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.aio import AIProjectClient as AsyncAIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
        credential = DefaultAzureCredential()
        project = AIProjectClient(endpoint=endpoint, credential=credential)
        worker_client = project.get_openai_client(timeout=30.0, max_retries=0)
        async_credential = AsyncDefaultAzureCredential()
        async_project = AsyncAIProjectClient(endpoint=endpoint, credential=async_credential)
        router_client = async_project.get_openai_client(timeout=30.0, max_retries=0)
        agent = cls(router_client.chat.completions, worker_client.responses, model)
        agent._clients = [worker_client, project, credential]
        agent._async_clients = [router_client, async_project, async_credential]
        return agent

    async def close(self) -> None:
        # Do not cancel coroutine wrappers around running executor calls.
        if self.workers:
            await asyncio.gather(*tuple(self.workers), return_exceptions=True)
        for client in self._async_clients:
            await client.close()
        for client in self._clients:
            await asyncio.to_thread(client.close)

    def start_worker(self, task: Task, history: list[dict[str, Any]]) -> None:
        worker = asyncio.create_task(run_worker(task, history, self.responses, self.model))
        self.workers.add(worker)
        worker.add_done_callback(self.workers.discard)

    async def respond(
        self,
        conversation: Conversation,
        turn: Turn,
        user_input: str,
    ) -> AsyncIterator[str]:
        # Evaluated only after the CE generation gate opens. Queued inputs do not
        # retain old history snapshots that can miss later heard_text corrections.
        # Share one bounded, chronological snapshot with Router and new Workers.
        # Drop whole older entries, never silently clip technical instructions.
        history = []
        remaining = MAX_MODEL_HISTORY_CHARACTERS
        for entry in reversed(conversation.history):
            if not entry.content:
                continue
            if len(entry.content) > remaining:
                break
            history.append({"type": "message", "role": entry.role, "content": entry.content})
            remaining -= len(entry.content)
        history.reverse()
        conversation.history.append(HistoryEntry("user", user_input))
        input_items = [*history, {"type": "message", "role": "user", "content": user_input}]
        store = conversation.tasks
        store.cleanup()
        completed = store.completed_tasks()
        # Keep references across Router I/O, including tasks that fail or get cancelled.
        active = store.active_tasks()
        context_parts = [
            build_task_context(store),
            "\n".join(
                f'Completed task {task.task_id} "{task.query}": {task.result}'
                for task in reversed(completed)
            ),
            "\n".join(
                f"Task {task.task_id}: {task_message(task)}" for task in store.terminal_tasks()
            ),
            build_delivered_context(store),
        ]
        context = "\n\n".join(part for part in context_parts if part)
        # Only complete result bodies in this request authorize Router delivery claims.
        # Do not let Worker completion during Router I/O grant that authority retroactively.
        visible_result_ids = {
            task.task_id for task in completed + store.delivered_tasks()
        }
        if len(context) > MAX_TASK_CONTEXT_CHARACTERS:
            # Do not present a clipped result as a complete, deliverable answer.
            visible_result_ids.clear()
            tasks = (
                active + list(reversed(completed))
                + store.terminal_tasks() + store.delivered_tasks()
            )
            context = "\n".join(
                f'{task.status.value.upper()} task {task.task_id}: "{task.query[:200]}"'
                for task in tasks
            )
            notice = (
                "\n[Result bodies omitted to fit task context. Use get_task_result for full "
                "retained results; do not guess or deliver partial results from this index.]"
            )
            context = context[:MAX_TASK_CONTEXT_CHARACTERS - len(notice)] + notice
        messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in input_items)
        if context:
            messages.insert(-1, {"role": "system", "content": context})
        response = await self.chat.create(
            model=self.model,
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {key: value for key, value in tool.items() if key != "type"},
                }
                for tool in ROUTER_TOOLS
            ],
            tool_choice=ROUTER_TOOL_CHOICE,
            parallel_tool_calls=False,
        )
        if not response.choices:
            raise ValueError("Router returned no choice")
        calls = response.choices[0].message.tool_calls or []
        if len(calls) != 1:
            raise ValueError("Router must return exactly one tool call")
        call = calls[0].function
        arguments = json.loads(call.arguments)
        if call.name == "respond_directly":
            message = arguments.get("message", "")
            reported = arguments.get("delivered_task_ids")
            if (
                not isinstance(reported, list)
                or any(not isinstance(task_id, str) for task_id in reported)
                or not set(reported).issubset(visible_result_ids)
            ):
                raise ValueError("Router returned invalid delivered task IDs")
            if not isinstance(message, str) or (reported and not message.strip()):
                raise ValueError("Router delivery claims require a nonblank spoken message")
            turn.delivered_task_ids.update(reported)
            active = [task for task in active if task.task_id not in turn.delivered_task_ids]
        else:
            result, new_task = execute_router_tool(call.name, arguments, store)
            data = json.loads(result)
            task = store.get(arguments.get("task_id", "latest"))
            if call.name == "start_task":
                if new_task is not None:
                    self.start_worker(
                        new_task,
                        [*history, {"type": "message", "role": "user", "content": new_task.query}],
                    )
                    active.append(new_task)
                    message = arguments.get("ack_message", "On it.")
                else:
                    message = "I'm busy; I haven't started another task."
            elif call.name == "cancel_task":
                message = (
                    (arguments.get("ack_message") or "Cancellation requested.")
                    if data["cancelled"]
                    else "There is no active work to cancel."
                )
            elif task is None:
                message = data.get("error", "No task found")
            elif task and task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.DELIVERED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                message = task_message(task)
                # This lookup already conveys the terminal outcome; do not repeat it below.
                active = [candidate for candidate in active if candidate is not task]
                if task.status is TaskStatus.COMPLETED:
                    turn.delivered_task_ids.add(task.task_id)
            else:
                message = arguments.get("ack_message") or data.get("error", "Still working on it.")
        for chunk in text_chunks(message):
            yield chunk
        has_output = bool(message)

        next_status = asyncio.get_running_loop().time() + STATUS_INTERVAL
        status_count = 0
        while any(task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING) for task in active):
            await asyncio.sleep(0.1)
            if asyncio.get_running_loop().time() < next_status or status_count >= 5:
                continue
            next_status = asyncio.get_running_loop().time() + STATUS_INTERVAL
            status_count += 1
            try:
                update = await asyncio.wait_for(
                    self.chat.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "Give a voice-friendly progress update of at most six words, "
                                    "in the user's language. Do not say task or tool."
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"User message (language reference): {user_input}\n"
                                    + "; ".join(
                                        f"{task.query}: round {task.rounds_completed + 1}, "
                                        f"current tool {task.current_tool or 'thinking'}"
                                        for task in active
                                        if task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
                                    )
                                ),
                            },
                        ],
                    ),
                    timeout=STATUS_TIMEOUT,
                )
                # Optional status output must not precede a newly ready result.
                if not any(t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING) for t in active):
                    break
                status = update.choices[0].message.content or ""
                if status and has_output:
                    yield "\n\n"
                for chunk in text_chunks(status):
                    yield chunk
                has_output = has_output or bool(status)
            except Exception as error:
                logger.warning("Status update skipped; error_type=%s", type(error).__name__)
        for task in active:
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.status is TaskStatus.COMPLETED:
                    turn.delivered_task_ids.add(task.task_id)
                if has_output:
                    yield "\n\n"
                for chunk in text_chunks(task_message(task)):
                    yield chunk
                has_output = True
