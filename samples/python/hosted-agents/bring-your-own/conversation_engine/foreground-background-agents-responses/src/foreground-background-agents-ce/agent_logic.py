"""Field Operations Agent — Two-Agent Architecture (Streaming).

Architecture:
  Router Agent — user-facing, always responds fast (< 2s).
                 Handles chat, delegates work, manages task lifecycle.
  Worker Agent — background tool executor. Runs multi-round tool loops
                 asynchronously. Supports cancellation between rounds.

Streaming behavior:
  - Worker always runs in background (resilient to disconnection).
  - While connected, the handler streams: ack → wait → result.
  - If disconnected mid-wait, worker keeps running. Next turn delivers the result.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (auto-injected)
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable
from contextlib import aclosing, asynccontextmanager
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.aio import AIProjectClient as AsyncAIProjectClient
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

from text_stream import TextEventStream
from task_store import TaskStatus
from router_agent import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_TOOLS,
    ROUTER_TOOL_CHOICE,
    build_task_context,
    build_delivered_context,
    execute_router_tool,
)
from worker_agent import run_worker

logger = logging.getLogger(__name__)

# ── Environment & Clients ─────────────────────────────────────────────────────

_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
if not _endpoint:
    raise EnvironmentError("FOUNDRY_PROJECT_ENDPOINT not set")

_model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
if not _model:
    raise EnvironmentError("AZURE_AI_MODEL_DEPLOYMENT_NAME not set")

_credential = DefaultAzureCredential()
_project_client = AIProjectClient(endpoint=_endpoint, credential=_credential)
_responses_client = _project_client.get_openai_client().responses

# ── Shared State ──────────────────────────────────────────────────────────────

_active_cancel_signals: dict[str, asyncio.Event] = {}  # response_id -> cancellation signal

import re

_DEBUG_TAG_RE = re.compile(r"^\[(?:Router|Router-Ack|Router-Result|Worker)\]\s*")


def _strip_debug_tags(text: str) -> str:
    """Remove debug tags from text before feeding back to the model."""
    return _DEBUG_TAG_RE.sub("", text)


def _build_input(current_input: str, history: list) -> list[dict]:
    """Convert conversation history + current input into LLM message format."""
    input_items = []
    for item in history:
        for content in item.get("content") or []:
            text = content.get("text")
            if content.get("type") == "output_text" and text:
                input_items.append({"type": "message", "role": "assistant", "content": _strip_debug_tags(text)})
            elif content.get("type") == "input_text" and text:
                input_items.append({"type": "message", "role": "user", "content": text})
    input_items.append({"type": "message", "role": "user", "content": current_input})
    return input_items


# ── Streaming Helpers ─────────────────────────────────────────────────────────

_TASK_POLL_INTERVAL = 0.1  # seconds between status checks while waiting


def _emit_text_item(stream: TextEventStream, text: str):
    """Keep the original 40-character chunks at the CE transport boundary."""
    return stream.text_events(text)


@asynccontextmanager
async def _router_client():
    # Keep the original Foundry project/authentication route; own all async resources per call.
    async with AsyncDefaultAzureCredential() as credential:
        async with AsyncAIProjectClient(endpoint=_endpoint, credential=credential) as project:
            async with project.get_openai_client() as client:
                yield client


async def _iter_llm_stream(responses_client, model, instructions, input_items, tools, tool_choice=None):
    """Stream Chat Completions asynchronously so response cancellation closes upstream I/O."""
    del responses_client
    from types import SimpleNamespace
    import time

    # Convert responses-API style input to chat completions messages
    messages = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    for item in input_items:
        if isinstance(item, dict):
            messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})

    create_kwargs: dict = {"model": model, "messages": messages, "stream": True}
    if tools:
        # Convert responses-API tool format to chat completions format
        cc_tools = []
        for t in tools:
            if t.get("type") == "function" and "function" not in t:
                cc_tools.append({
                    "type": "function",
                    "function": {k: v for k, v in t.items() if k != "type"},
                })
            else:
                cc_tools.append(t)
        create_kwargs["tools"] = cc_tools
    if tool_choice:
        create_kwargs["tool_choice"] = tool_choice

    _stream_start = time.monotonic()
    accumulated_tool_calls: dict = {}  # index -> {id, name, arguments}
    has_text = False
    async with _router_client() as client:
        async with await client.chat.completions.create(**create_kwargs) as stream:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                # Text content
                if delta.content:
                    has_text = True
                    yield SimpleNamespace(type="response.output_text.delta", delta=delta.content)

                # Tool call deltas (accumulated across chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            accumulated_tool_calls[idx]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                if choice.finish_reason:
                    break

    if has_text:
        yield SimpleNamespace(type="response.output_text.done")
    for idx in sorted(accumulated_tool_calls):
        tc_data = accumulated_tool_calls[idx]
        yield SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="function_call", name=tc_data["name"],
                                 arguments=tc_data["arguments"], call_id=tc_data["id"]),
        )

    _stream_elapsed = time.monotonic() - _stream_start
    logger.info("LLM stream (chat completions) finished in %.1fms", _stream_elapsed * 1000)


# ── Request Handler ───────────────────────────────────────────────────────────

async def handler(
    request: dict[str, Any],
    context: Any,
    _cancellation_signal: asyncio.Event,
) -> AsyncIterable[dict[str, Any]]:
    _store = context.task_store
    _background_tasks = context.background_tasks
    user_input = await context.get_input_text() or "Hello!"
    history = await context.get_history()
    input_items = _build_input(user_input, history)

    # Register cancel signal so middleware can find it
    _active_cancel_signals[context.response_id] = _cancellation_signal

    logger.info("Processing request %s", context.response_id)

    stream = TextEventStream(
        response_id=context.response_id,
        request=request,
    )

    yield stream.emit_created()
    yield stream.emit_in_progress()

    try:
        # ── Collect previously completed task results ──
        completed = _store.collect_completed()
        completed_context = ""
        if completed:
            parts = [f"Completed task \"{t.query}\": {t.result}" for t in completed]
            completed_context = "\n".join(parts)

        # Cleanup old tasks
        _store.cleanup()

        # Inject context: running tasks + completed results + delivered history for router to reference
        context_parts = []
        task_context = build_task_context(_store)
        if task_context:
            context_parts.append(f"[INFO — do not mention to user unless asked] Running tasks:\n{task_context}")
        if completed_context:
            context_parts.append(f"Recently completed (deliver these results to the user):\n{completed_context}")
        delivered_context = build_delivered_context(_store)
        if delivered_context:
            context_parts.append(f"Recently delivered (already shown to user — use respond_directly to recall if asked):\n{delivered_context}")
        if context_parts:
            input_items.insert(-1, {"type": "message", "role": "system", "content": "\n\n".join(context_parts)})

        # ── Router Agent: single LLM call with tool_choice=required ──
        tool_calls = []

        async with aclosing(_iter_llm_stream(
            _responses_client, _model, ROUTER_SYSTEM_PROMPT, input_items, ROUTER_TOOLS,
            tool_choice=ROUTER_TOOL_CHOICE,
        )) as router_stream:
            async for event in router_stream:
                event_type = getattr(event, "type", None)
                if event_type == "response.output_item.done":
                    if getattr(event.item, "type", None) == "function_call":
                        tool_calls.append(event.item)

        if not tool_calls:
            # Fallback (shouldn't happen with tool_choice=required)
            for evt in _emit_text_item(stream, "How can I help?"):
                yield evt
            yield stream.emit_completed()
            return

        # ── Dispatch based on which tool the router chose ──
        tc = tool_calls[0]
        arguments = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
        tool_name = tc.name
        logger.info("Router tool selected")

        if tool_name == "respond_directly":
            # Pure chat — stream the message from arguments
            message = arguments.get("message", "")
            for evt in _emit_text_item(stream, message):
                yield evt

        elif tool_name == "start_task":
            # Admit conversation-owned work before yielding an interruptible acknowledgment.
            _, new_task = execute_router_tool("start_task", arguments, _store)
            if new_task is None:
                # The single-worker guard can reject a different request as well as a duplicate.
                for evt in _emit_text_item(stream, "I'm still working on an earlier request. I haven't started a new task."):
                    yield evt
                yield stream.emit_completed()
                return
            if new_task:
                logger.info("Starting worker for task %s", new_task.task_id)
                worker_input = _build_input(new_task.query, history)
                task_handle = asyncio.create_task(run_worker(new_task, worker_input, _responses_client, _model))
                _background_tasks.add(task_handle)
                task_handle.add_done_callback(_background_tasks.discard)

            ack = arguments.get("ack_message", "On it.")
            for evt in _emit_text_item(stream, ack):
                yield evt

        elif tool_name == "check_task_status":
            result_text, _ = execute_router_tool("check_task_status", arguments, _store)
            ack = arguments.get("ack_message", "")
            result_data = json.loads(result_text)
            # If task is completed/delivered, include the result in the response
            task_obj = _store.get(arguments.get("task_id", "latest"))
            if task_obj and task_obj.status in (TaskStatus.COMPLETED, TaskStatus.DELIVERED) and task_obj.result:
                msg = ack + "\n\n" + task_obj.result if ack else task_obj.result
            else:
                msg = ack or f"Task {result_data.get('task_id', '?')}: {result_data.get('status', 'unknown')}"
            for evt in _emit_text_item(stream, msg):
                yield evt

        elif tool_name == "cancel_task":
            result_text, _ = execute_router_tool("cancel_task", arguments, _store)
            ack = arguments.get("ack_message", "Cancelled.")
            for evt in _emit_text_item(stream, ack):
                yield evt

        elif tool_name == "get_task_result":
            result_text, _ = execute_router_tool("get_task_result", arguments, _store)
            result_data = json.loads(result_text)
            msg = result_data.get("result") or result_data.get("error", "No result yet.")
            for evt in _emit_text_item(stream, msg):
                yield evt

        else:
            for evt in _emit_text_item(stream, "I'm not sure how to help with that."):
                yield evt

        # ── Wait for active tasks ──
        # Wait for any running/queued tasks to finish (including ones from prior turns).
        # If cancel signal fires, just stop waiting — workers keep running and
        # results are delivered next turn via collect_completed().
        active = _store.active_tasks()
        if active:
            logger.info("Waiting for %d active task(s): %s", len(active), [t.task_id for t in active])
            _wait_start = asyncio.get_event_loop().time()
            _last_status_time = _wait_start
            _status_count = 0
            _STATUS_UPDATE_INTERVAL = 5.0  # seconds between status updates
            _MAX_STATUS_UPDATES = 5  # cap to avoid infinite status spam

            while not _cancellation_signal.is_set():
                await asyncio.sleep(_TASK_POLL_INTERVAL)
                # Check if all active tasks have resolved
                if all(t.status in (TaskStatus.COMPLETED, TaskStatus.DELIVERED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                       for t in active):
                    break

                # Emit an LLM-generated status update periodically while waiting
                # This should be work multiple times if tasks take a long time
                now = asyncio.get_event_loop().time()
                if _status_count < _MAX_STATUS_UPDATES and (now - _last_status_time) >= _STATUS_UPDATE_INTERVAL:
                    _last_status_time = now
                    _status_count += 1
                    # Build a brief status summary for the LLM
                    task_summaries = "; ".join(
                        f"'{t.query}' (step {t.rounds_completed + 1}, tool: {t.current_tool or 'thinking'})"
                        for t in active if t.status == TaskStatus.RUNNING
                    )
                    # Include recent user messages so the LLM matches the user's language
                    recent_user_msgs = [
                        m["content"] for m in input_items
                        if isinstance(m, dict) and m.get("role") == "user"
                    ][-3:]  # last 3 user messages for language context
                    language_hint = " | ".join(recent_user_msgs)
                    status_prompt = [
                        {"type": "message", "role": "system", "content": (
                            "Generate a very short status update (max 6 words, voice-friendly) "
                            "for a technician waiting on background work. Do NOT say 'task' or 'tool'. "
                            "Examples: 'Still working on it.' / 'Almost done.' / 'Pulling that up now.' "
                            "IMPORTANT: Reply in the SAME LANGUAGE as the user's messages below."
                        )},
                        {"type": "message", "role": "user", "content": (
                            f"User's recent messages (for language reference): {language_hint}\n\n"
                            f"Work in progress: {task_summaries}"
                        )},
                    ]
                    try:
                        status_text = ""
                        async with aclosing(_iter_llm_stream(
                            _responses_client, _model, None, status_prompt, tools=None,
                        )) as status_stream:
                            async for evt in status_stream:
                                if getattr(evt, "type", None) == "response.output_text.delta":
                                    status_text += evt.delta
                        if status_text.strip():
                            for evt in _emit_text_item(stream, status_text.strip()):
                                yield evt
                    except Exception as e:
                        logger.warning("Status update LLM call failed; error_type=%s", type(e).__name__)

            # Deliver results for tasks that finished while we were waiting
            if not _cancellation_signal.is_set():
                for task in active:
                    if task.status == TaskStatus.COMPLETED and task.result:
                        # Claim synchronously, before yielding: only one waiter delivers the result.
                        task.status = TaskStatus.DELIVERED
                        for evt in _emit_text_item(stream, task.result):
                            yield evt
                    elif task.status == TaskStatus.FAILED:
                        for evt in _emit_text_item(stream, f"Something went wrong: {task.result}"):
                            yield evt
            else:
                logger.info("Cancel signal received — stopping SSE, workers continue in background")

        yield stream.emit_completed()
        logger.info("Finished processing request %s", context.response_id)

    except Exception as exc:
        logger.error("Handler failed; error_type=%s", type(exc).__name__)
        for evt in _emit_text_item(stream, f"Sorry, something went wrong: {exc}"):
            yield evt
        yield stream.emit_completed()
    finally:
        _active_cancel_signals.pop(context.response_id, None)
