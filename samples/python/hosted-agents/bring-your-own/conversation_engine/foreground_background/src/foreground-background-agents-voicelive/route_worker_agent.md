# Router + Worker Agent Design

## Overview

A two-agent architecture where the **Router** handles user interaction using an asynchronous
Chat Completions call, and the **Worker** retains the background Responses/tool loop.
Hosted ingress is now the CE WebSocket protocol, not the Responses HTTP protocol.

## Router Agent

- Receives every user message and makes an initial LLM call with `tool_choice: required`.
- Must select exactly one meta-tool in that initial routing request.
- Successful result/status retrieval then makes at most one tool-free presentation call.
  The full retrieved body and current user request let it translate, summarize, or relay
  the result; it cannot start more work. This is separate from optional progress calls.
- Meta-tools:
  - `respond_directly` — greetings, chat, clarifications, delivering results
  - `start_task` — delegate actionable field-ops work to the Worker
  - `check_task_status` — report progress of a running task
  - `cancel_task` — cancel a running task
  - `get_task_result` — retrieve a completed task's result
- Guards against duplicate tasks: if a task is already active, `start_task` returns the existing task instead of creating a new one.
- Injected context each turn: running tasks, recently completed results, previously delivered results.

## Worker Agent

- Runs in an independently retained `asyncio.create_task`.
- Executes a multi-round tool-calling loop (up to 5 rounds) using domain tools:
  - `search_site_specs` — site specification lookup
  - `search_work_iq` — Teams/Outlook/People search
  - `get_repair_procedure` — step-by-step maintenance procedures
  - `analyze_document` — document understanding and extraction
- Writes results into the shared `Task` object (never talks to the user directly).
- Supports cancellation between rounds via `cancel_event`.
- Survives foreground interruption within a connection. Session end/disconnect requests
  cooperative cancellation; shutdown joins retained Workers after their in-flight call settles.

## Task Store

- In-memory registry tracking task lifecycle: `QUEUED → RUNNING → COMPLETED → DELIVERED`.
- Explicit task IDs (including paraphrases) are marked delivered after a successful CE
  `response.done` send, not during result collection or by substring matching.
- `delivered_tasks()` exposes history so the Router can recall past results on follow-up questions.

## Streaming & Wait Behavior

- Handler streams: acknowledgment → wait for active tasks → deliver results.
- Business cancellation is acknowledgment-only: this turn does not wait for or deliver
  Worker outcomes. An in-flight final answer is retained for a later request.
- Result/status lookup may wait for its Worker, then presents its complete result according
  to the current user request. Only successfully sent presentation text enters history;
  the model explicitly reports whether that text conveys the result. Status-only answers
  leave results pending. Only a result-conveying answer plus successful `response.done`
  commits delivery. Failed/interrupted presentation can retry.
- While waiting, optional status updates run every five seconds, up to five times, with a
  one-second model deadline. A newly ready result takes precedence over optional status speech.
- Foreground cancellation stops that CE response. Workers continue until they finish or the
  business task/session requests cancellation; another turn on the same connection can deliver results.
- Task state and bounded caller-heard history are isolated per connection; they are not durable
  or resumed across disconnected sockets.
