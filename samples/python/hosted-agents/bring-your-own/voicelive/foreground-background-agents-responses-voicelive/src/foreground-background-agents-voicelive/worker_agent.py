"""Worker Agent — background tool executor.

Runs the multi-round tool-calling loop asynchronously. Supports cancellation
between rounds and reports progress to the shared TaskStore.

This agent never talks to the user directly — it writes results into the Task.
"""

import asyncio
import json
import logging

from task_store import Task, TaskStatus

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 5

_WORKER_SYSTEM_PROMPT = """You are a field operations AI assistant for data center technicians at Microsoft.

You help on-site technicians with:
- Looking up site specifications and fiber termination details
- Finding relevant context from Teams and Outlook (Work IQ)
- Retrieving repair and maintenance procedures
- Analyzing technical documents and schematics

You are voice-enabled — technicians talk to you hands-free while working on site.
Keep responses concise and actionable. When referencing technical details, be specific
about panel numbers, rack locations, and fiber types.

Always cross-reference multiple sources when available — check both site specs AND
recent communications to give the most up-to-date answer."""

# ── Domain Tools ──────────────────────────────────────────────────────────────

DOMAIN_TOOLS = [
    {
        "type": "function",
        "name": "search_site_specs",
        "description": "Search site specification documents for a data center site. Returns technical details about fiber panels, network topology, power systems, and site layout.",
        "parameters": {
            "type": "object",
            "properties": {
                "site_name": {"type": "string", "description": "Name of the data center site (e.g., 'Quincy North', 'East US DC-7')"},
                "query": {"type": "string", "description": "What to search for in the site specs"},
            },
            "required": ["site_name", "query"],
        },
    },
    {
        "type": "function",
        "name": "search_work_iq",
        "description": "Search Work IQ (Microsoft 365) for relevant context from Teams messages, Outlook emails, and People directory. Returns recent communications about a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for Teams/Outlook/People"},
                "source": {"type": "string", "enum": ["teams", "outlook", "people", "all"], "description": "Which Work IQ source to search"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_repair_procedure",
        "description": "Retrieve a repair or maintenance procedure from procedural memory. Returns step-by-step instructions learned from past incidents.",
        "parameters": {
            "type": "object",
            "properties": {
                "procedure_type": {"type": "string", "description": "Type of procedure (e.g., 'fiber_splice', 'panel_replacement', 'power_failover')"},
                "site_name": {"type": "string", "description": "Optional site name for site-specific procedures"},
            },
            "required": ["procedure_type"],
        },
    },
    {
        "type": "function",
        "name": "analyze_document",
        "description": "Use Document Understanding to analyze a technical document, schematic, or form. Extracts structured data from complex multi-page documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Document identifier or name"},
                "question": {"type": "string", "description": "What to extract or analyze from the document"},
            },
            "required": ["document_id", "question"],
        },
    },
]

# ── Mock Tool Implementations ─────────────────────────────────────────────────
# Feature teams replace these with real backends.

_MOCK_RESPONSES = {
    "search_site_specs": lambda args: json.dumps({
        "site": args.get("site_name", "Unknown"),
        "results": [
            {
                "title": f"Fiber Termination Spec — {args.get('site_name', 'Site')}",
                "content": f"Panel layout for {args.get('site_name', 'site')}: "
                           f"A-side connections on panels 1-12 (single-mode OS2), "
                           f"B-side connections on panels 13-24 (multi-mode OM4). "
                           f"Cross-connect patch panel is in Row C, Rack 7. "
                           f"Last updated: 2026-04-15.",
            },
            {
                "title": f"Network Topology — {args.get('site_name', 'Site')}",
                "content": "Primary uplink: 100G to regional hub via dark fiber pair F-201/F-202. "
                           "Redundant path: 40G via carrier XYZ on diverse route.",
            },
        ],
    }),
    "search_work_iq": lambda args: json.dumps({
        "source": args.get("source", "all"),
        "results": [
            {
                "type": "teams_message",
                "from": "Sarah Chen (Site Supervisor)",
                "date": "2026-05-10",
                "content": f"Re: {args.get('query', 'topic')} — Confirmed the B-side panels "
                           f"were re-terminated last week. New fiber map is in the site binder.",
            },
            {
                "type": "outlook_email",
                "from": "Network Operations",
                "date": "2026-05-09",
                "subject": "Maintenance Window Completed",
                "snippet": "All splice work completed on the north campus fiber ring.",
            },
        ],
    }),
    "get_repair_procedure": lambda args: json.dumps({
        "procedure": args.get("procedure_type", "general"),
        "steps": [
            "1. Verify affected circuit using OTDR test from patch panel",
            "2. Identify splice point using fiber map (Row C, Rack 7)",
            "3. Clean all connectors with IPA wipes before re-termination",
            "4. Use fusion splicer for single-mode (OS2) connections",
            "5. Verify continuity with visual fault locator",
            "6. Run OTDR baseline and compare to previous readings",
            "7. Update fiber map and close work order",
        ],
        "notes": "Learned from 47 previous incidents at this site type.",
    }),
    "analyze_document": lambda args: json.dumps({
        "document": args.get("document_id", "unknown"),
        "analysis": f"Document analysis for '{args.get('document_id', 'doc')}': "
                    f"This is a multi-page site specification containing fiber topology diagrams, "
                    f"power distribution schematics, and equipment inventory. "
                    f"Key finding: {args.get('question', 'N/A')}",
        "extracted_data": {
            "total_pages": 47,
            "diagrams": 12,
            "tables": 8,
        },
    }),
}


def _execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return the result string (with simulated latency)."""
    import time
    import random
    time.sleep(random.randint(6, 12))  # simulate network/service latency for testing
    handler = _MOCK_RESPONSES.get(name)
    if handler:
        return handler(arguments)
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Worker Loop ───────────────────────────────────────────────────────────────


async def run_worker(task: Task, input_items: list[dict], responses_client, model: str):
    """Run the tool-calling loop in the background for a given task.

    Updates task.status/current_tool/result as it progresses.
    Checks task.cancel_event between rounds — but always finishes the current
    in-flight operation so its result is preserved. The handler doesn't block
    on the worker (it's fire-and-forget via asyncio.create_task), so client
    disconnect doesn't affect us. Result is delivered on the next turn.
    """
    task.status = TaskStatus.RUNNING
    loop = asyncio.get_running_loop()

    try:
        for round_num in range(_MAX_TOOL_ROUNDS):
            # ── Cancellation checkpoint (between rounds) ──
            if task.cancel_event.is_set():
                task.status = TaskStatus.CANCELLED
                task.result = "(Cancelled by user)"
                return

            task.rounds_completed = round_num

            # ── LLM call ──
            response = await loop.run_in_executor(
                None,
                lambda: responses_client.create(
                    model=model,
                    instructions=_WORKER_SYSTEM_PROMPT,
                    input=input_items,
                    tools=DOMAIN_TOOLS,
                    store=False,
                ),
            )

            # Check cancel after LLM completes
            if task.cancel_event.is_set():
                # LLM finished — save partial result if it's a final answer
                text = response.output_text
                if text and not [i for i in response.output if getattr(i, "type", None) == "function_call"]:
                    task.status = TaskStatus.COMPLETED
                    task.result = text
                else:
                    task.status = TaskStatus.CANCELLED
                    task.result = "(Cancelled by user)"
                return

            tool_calls = [
                item for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]

            # No tool calls → model produced final answer
            if not tool_calls:
                task.status = TaskStatus.COMPLETED
                task.result = response.output_text or "(No response)"
                return

            # ── Execute each tool call ──
            for tc in tool_calls:
                task.current_tool = tc.name

                try:
                    arguments = (
                        json.loads(tc.arguments)
                        if isinstance(tc.arguments, str)
                        else tc.arguments
                    )
                    result_text = await loop.run_in_executor(
                        None, _execute_tool, tc.name, arguments
                    )
                    logger.info("Tool '%s' returned %d chars", tc.name, len(result_text))
                except Exception as e:
                    logger.error("Tool '%s' failed: %s", tc.name, e)
                    result_text = f"Error: {e}"

                input_items.append({
                    "type": "function_call",
                    "id": tc.id,
                    "call_id": tc.call_id,
                    "name": tc.name,
                    "arguments": (
                        tc.arguments
                        if isinstance(tc.arguments, str)
                        else json.dumps(tc.arguments)
                    ),
                })
                input_items.append({
                    "type": "function_call_output",
                    "call_id": tc.call_id,
                    "output": result_text,
                })

                # Check cancel between tool calls
                if task.cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    task.result = "(Cancelled by user)"
                    return

            task.current_tool = None

        # Exhausted all rounds
        task.status = TaskStatus.COMPLETED
        task.result = "(Reached maximum tool call rounds)"

    except Exception as e:
        logger.exception("Worker failed for task %s", task.task_id)
        task.status = TaskStatus.FAILED
        task.result = f"(Worker error: {e})"
