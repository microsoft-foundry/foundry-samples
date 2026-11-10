# Router + Worker Agent Design

## Overview

A two-agent architecture where the **Router** handles all user interaction (fast, always responsive) and the **Worker** executes tool-calling loops in the background (async, cancelable).

## Router Agent

- Receives every user message and makes a single LLM call with `tool_choice: required`.
- Must call exactly one of its meta-tools per turn — no free-text output path.
- Meta-tools:
  - `respond_directly` — greetings, chat, clarifications, delivering results
  - `start_task` — delegate actionable field-ops work to the Worker
  - `check_task_status` — report progress of a running task
  - `cancel_task` — cancel a running task
  - `get_task_result` — retrieve a completed task's result
- Guards against duplicate tasks: if a task is already active, `start_task` returns the existing task instead of creating a new one.
- Injected context each turn: running tasks, recently completed results, previously delivered results.

## Worker Agent

- Runs asynchronously via `asyncio.create_task` (fire-and-forget).
- Executes a multi-round tool-calling loop (up to 5 rounds) using domain tools:
  - `search_site_specs` — site specification lookup
  - `search_work_iq` — Teams/Outlook/People search
  - `get_repair_procedure` — step-by-step maintenance procedures
  - `analyze_document` — document understanding and extraction
- Writes results into the shared `Task` object (never talks to the user directly).
- Supports cancellation between rounds via `cancel_event`.
- Resilient to client disconnection — keeps running in background.

## Task Store

- In-memory registry tracking task lifecycle: `QUEUED → RUNNING → COMPLETED → DELIVERED`.
- `collect_completed()` atomically collects finished results and marks them delivered (exactly-once delivery).
- `delivered_tasks()` exposes history so the Router can recall past results on follow-up questions.

## Streaming & Wait Behavior

- Handler streams: acknowledgment → wait for active tasks → deliver results.
- While waiting, periodic LLM-generated status updates are streamed (every ~8s, up to 5 times) in the user's language.
- If cancel signal fires mid-wait, the SSE closes but workers continue — results are delivered next turn.
