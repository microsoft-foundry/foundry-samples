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

    def reconcile(self, response_id: str, heard_text: str) -> None:
        for entry in self.history:
            if entry.response_id == response_id:
                entry.content = heard_text
                return
        if heard_text:
            # A send may still be unwinding when the caller-heard event arrives.
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
        history = [
            {"type": "message", "role": entry.role, "content": entry.content}
            for entry in conversation.history
            if entry.content
        ]
        conversation.history.append(HistoryEntry("user", user_input))
        input_items = [*history, {"type": "message", "role": "user", "content": user_input}]
        store = conversation.tasks
        store.cleanup()
        completed = store.completed_tasks()
        context_parts = [
            build_task_context(store),
            build_delivered_context(store),
            "\n".join(
                f'Completed task {task.task_id} "{task.query}": {task.result}' for task in completed
            ),
            "\n".join(
                f"Task {task.task_id}: {task_message(task)}" for task in store.terminal_tasks()
            ),
        ]
        context = "\n\n".join(part for part in context_parts if part)
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
            reported = arguments.get("delivered_task_ids", [])
            turn.delivered_task_ids.update(
                task.task_id for task in completed if task.task_id in reported
            )
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
                message = arguments.get("ack_message", "On it.")
            elif call.name == "cancel_task":
                message = (
                    (arguments.get("ack_message") or "Cancellation requested.")
                    if data["cancelled"]
                    else "There is no active work to cancel."
                )
            elif task and task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.DELIVERED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                message = task_message(task)
                if task.status is TaskStatus.COMPLETED:
                    turn.delivered_task_ids.add(task.task_id)
            else:
                message = arguments.get("ack_message") or data.get("error", "Still working on it.")
        active = store.active_tasks()
        # Results may become ready during Router I/O, after its context was built.
        # Do not repeat results the Router saw or a status/result lookup just emitted.
        known_completed = {task.task_id for task in completed}
        active.extend(
            task for task in store.completed_tasks()
            if task.task_id not in known_completed and task.task_id not in turn.delivered_task_ids
        )
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
