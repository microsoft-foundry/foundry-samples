"""Router Agent — function-routing pattern with tool_choice: required.

Every router turn MUST produce exactly one tool call. No free-text path exists.
This eliminates "hallucinated action" where the LLM says "looking into it" without
actually delegating.

Tools:
  respond_directly — for chat, greetings, delivering completed results
  start_task       — delegate field-ops work to worker (includes ack_message)
  check_task_status / cancel_task / get_task_result — meta-operations
"""

import json
import logging

from task_store import Task, TaskStatus, TaskStore

logger = logging.getLogger(__name__)
TASK_UNAVAILABLE_MESSAGE = "No task found (it may have expired or been evicted)."

# ── Router Tools ──────────────────────────────────────────────────────────────
# The caller also sets parallel_tool_calls=False and validates exactly one call.

ROUTER_TOOLS = [
    {
        "type": "function",
        "name": "respond_directly",
        "description": (
            "Respond to the user directly without delegating. "
            "Use for: greetings, chat, clarifications, delivering completed results, "
            "or any response that does NOT require background tool execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The spoken response to the user. Keep concise for voice.",
                },
                "delivered_task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "IDs of retained completed or already-delivered tasks whose results this "
                        "message conveys, including paraphrases and translations. "
                        "Empty for unrelated chat."
                    ),
                },
            },
            "required": ["message", "delivered_task_ids"],
        },
    },
    {
        "type": "function",
        "name": "start_task",
        "description": (
            "Delegate a field-ops request to the background worker agent. "
            "Use for: site specs lookup, Work IQ search, repair procedures, "
            "document analysis — anything requiring tool execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_summary": {
                    "type": "string",
                    "description": "Clear summary of what the user needs done",
                },
                "ack_message": {
                    "type": "string",
                    "description": (
                        "Very short spoken acknowledgment, max 5-6 words (e.g. 'Looking that up"
                        ".' or 'On it.')"
                    ),
                },
            },
            "required": ["request_summary", "ack_message"],
        },
    },
    {
        "type": "function",
        "name": "check_task_status",
        "description": (
            "Check progress of a running or completed task. "
            "Use when the user asks about status or progress."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID, or 'latest' for most recent task",
                },
                "ack_message": {
                    "type": "string",
                    "description": "Brief spoken response about the status",
                },
            },
            "required": ["task_id", "ack_message"],
        },
    },
    {
        "type": "function",
        "name": "cancel_task",
        "description": "Cancel a running or queued task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to cancel, or 'latest'",
                },
                "ack_message": {
                    "type": "string",
                    "description": "Brief spoken confirmation to the user",
                },
            },
            "required": ["task_id", "ack_message"],
        },
    },
    {
        "type": "function",
        "name": "get_task_result",
        "description": (
            "Retrieve the final result of a completed task. "
            "Use when a task has finished and you need to relay the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID, or 'latest'",
                },
            },
            "required": ["task_id"],
        },
    },
]

# Force the model to always call a tool (no free-text path)
ROUTER_TOOL_CHOICE = "required"

ROUTER_SYSTEM_PROMPT = (
    "You are the front-desk assistant for field operations technicians at M"
    "icrosoft data centers.\n\nYou MUST call exactly one function per turn. Y"
    "ou cannot respond with plain text.\nWhen respond_directly conveys compl"
    "eted results, include their exact task IDs in\ndelivered_task_ids. Incl"
    "ude only results actually conveyed in message; use [] for\nunrelated ch"
    "at, acknowledgments, or status-only replies.\n\nFUNCTION SELECTION:\n- re"
    "spond_directly: greetings, chat, clarifications, capability questions,"
    " delivering completed results, acknowledging user, answering from conv"
    "ersation history, ANY question unrelated to field-ops\n- start_task: us"
    "er provides a COMPLETE, ACTIONABLE field-ops request (they've given en"
    "ough info to act on)\n- check_task_status: user asks about progress of "
    "a running task\n- cancel_task: user wants to stop a task\n- get_task_res"
    "ult: retrieve a finished task's result that hasn't been shown yet\n\nWHE"
    'N TO USE start_task vs respond_directly:\n- "Analyze document 12345" → '
    'start_task (actionable: document ID is provided)\n- "Can you analyze a '
    'document?" → respond_directly (capability question, no document specif'
    'ied)\n- "Search site specs for Quincy North" → start_task (actionable: '
    'site name provided)\n- "Can you look stuff up?" → respond_directly (no '
    'specific request)\n- "How old are you?" / "What\'s the weather?" → respo'
    'nd_directly (unrelated to field-ops)\n- "Great" / "Thanks" → respond_di'
    "rectly (acknowledgment)\n\nRULES:\n1. For greetings/chat/thanks/acknowled"
    'gments ("Great", "OK", "Thank you", "Got it", "Perfect", etc.) → ALWAY'
    "S call respond_directly. NEVER re-trigger a task for these.\n2. For que"
    "stions UNRELATED to field operations (personal questions, general know"
    "ledge, small talk) → ALWAYS call respond_directly, regardless of any r"
    "unning tasks.\n3. Only call start_task when the user provides a SPECIFI"
    "C, ACTIONABLE request with enough parameters to execute (e.g., a docum"
    "ent ID, a site name, a procedure type). If key information is missing,"
    " call respond_directly to ask for it.\n4. Do NOT call start_task if a r"
    'unning task already covers the same request (check "Running tasks" con'
    "text).\n5. Do NOT call start_task if the user is referring to a result "
    "that was ALREADY delivered. If the result is in conversation history o"
    'r in "Recently delivered" context, call respond_directly and re-state '
    'it. If result bodies were omitted, use get_task_result instead.\n6. If "Recently completed" '
    "results exist in context, call respond_"
    "directly and include those results naturally in your message.\n7. If th"
    "e user asks to recall/replay/repeat a previous result, look at convers"
    'ation history or "Recently delivered" context and call respond_directl'
    "y with that information. If only a task index is available, use get_task_result; "
    "never infer missing result details.\n8. Match the user's language. Keep messages c"
    "oncise (voice-enabled, hands-free).\n9. When the user's message has BOT"
    "H chat and a NEW actionable field-ops request, call start_task (the ac"
    "k_message handles the conversational part).\n\nIMPORTANT: A message like"
    ' "Great", "Thanks", "OK" after a delivered result is just the user ack'
    "nowledging — respond with something brief and friendly. Do NOT re-run "
    "the task.\nIMPORTANT: If there is a running task and the user says some"
    "thing UNRELATED, just respond with respond_directly. Do NOT create a n"
    "ew task.\n\nSTYLE: concise, helpful, technical when needed. The technici"
    "an is working hands-free."
)


# ── Router Tool Execution ─────────────────────────────────────────────────────


def execute_router_tool(name: str, arguments: dict, store: TaskStore) -> tuple[str, Task | None]:
    """Execute a router meta-tool. Returns (result_json, new_task_or_none).

    All operations here are instant (no I/O, no blocking).
    """
    if name == "respond_directly":
        return json.dumps({"delivered": True}), None

    if name == "start_task":
        # Guard: don't create a duplicate task if one is already active
        active = store.active_tasks()
        if active:
            existing = active[-1]  # most recent active task
            return json.dumps(
                {
                    "task_id": existing.task_id,
                    "status": existing.status.value,
                    "note": "Task already running — not creating duplicate",
                    "query": existing.query,
                }
            ), None  # Return None → no new worker spawned
        task = store.create_task(arguments["request_summary"])
        return json.dumps({"task_id": task.task_id, "status": "queued"}), task

    if name == "check_task_status":
        task = store.get(arguments["task_id"])
        if not task:
            return json.dumps({"error": TASK_UNAVAILABLE_MESSAGE}), None
        return json.dumps(
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "current_tool": task.current_tool,
                "rounds_completed": task.rounds_completed,
                "query": task.query,
            }
        ), None

    if name == "cancel_task":
        success = store.cancel(arguments["task_id"])
        task = store.get(arguments["task_id"])
        return json.dumps(
            {
                "cancelled": success,
                "task_id": task.task_id if task else None,
            }
        ), None

    if name == "get_task_result":
        task = store.get(arguments["task_id"])
        if not task:
            return json.dumps({"error": TASK_UNAVAILABLE_MESSAGE}), None
        if task.status in (TaskStatus.COMPLETED, TaskStatus.DELIVERED):
            return json.dumps({"task_id": task.task_id, "result": task.result}), None
        return json.dumps(
            {
                "error": "Task not completed yet",
                "task_id": task.task_id,
                "status": task.status.value,
            }
        ), None

    return json.dumps({"error": f"Unknown router tool: {name}"}), None


def build_task_context(store: TaskStore) -> str | None:
    """Build a context string about active tasks for the router prompt."""
    lines = []
    for t in store.active_tasks():
        lines.append(
            f"RUNNING: task {t.task_id} — '{t.query}' "
            f"(round {t.rounds_completed + 1}, tool: {t.current_tool or 'thinking'})"
        )
    return "\n".join(lines) if lines else None


def build_delivered_context(store: TaskStore) -> str | None:
    """Build a context string of recently delivered task results.

    This helps the router recall results that were already shown to the user,
    so it can respond to follow-ups like 'what was the result?' without re-running.
    """
    lines = []
    for t in store.delivered_tasks():
        # The caller budgets the entire task context and requests lookup if it does not fit.
        lines.append(f"DELIVERED: task {t.task_id} — '{t.query}' → {t.result or ''}")
    return "\n".join(lines) if lines else None
