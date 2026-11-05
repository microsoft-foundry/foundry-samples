<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Resilient Copilot — a long-running, crash-resilient GitHub Copilot agent

A **real GitHub Copilot agent** made **durable, survivable, and reconnectable** by
the resilient `@multi_turn_task` primitive. The [GitHub Copilot SDK](https://pypi.org/project/github-copilot-sdk/)
is the agent brain — it runs its own model + tool-calling loop — and
[`azure-ai-agentserver-core`](https://pypi.org/project/azure-ai-agentserver-core/)
is the *hosting envelope* that keeps that brain alive across idle periods and
container crashes, over the [invocations protocol](https://pypi.org/project/azure-ai-agentserver-invocations/).

Unlike a getting-started Copilot sample, this one wires up the **five
long-running-agent capabilities** end-to-end on a genuine agent loop.

## Capabilities

| Capability | What it gives you | How it works here |
|---|---|---|
| **Long-running / no-ingress survival** | Work keeps running past idle-eviction even with no client connected. | While the Copilot agent grinds through a (possibly minutes-long) tool loop, the task is `in_progress`, so the platform keeps the container alive. |
| **Crash recovery** | A replacement container restores the latest saved Copilot session. | On recovered entry, the task restores the session snapshot from `FoundryStateStore` before calling `resume_session(session_id)` and re-driving the prompt. Uncheckpointed work can repeat. |
| **Continuation checkpoints** | Todo, plan and declared required-file changes are saved within a turn. | A post-tool hook waits for the required-only session snapshot; the stream emits `todo_checkpoint` only after persistence succeeds. |
| **Steering** | A new input redirects the in-flight turn instead of racing it. | Accepted inputs are persisted before HTTP acknowledgement and delivered through Copilot's native `send(mode="immediate")`. Interrupted delivery can replay. |
| **Queueing** | A follow-up input runs after the current turn. | Durable acceptance and native `send(mode="enqueue")` preserve follow-ups; recovery is at-least-once, not exactly-once delivery. |
| **Streaming with reconnect** | Clients reconnect after a drop or crash with no gap. | Every Copilot `SessionEvent` is emitted onto a **file-backed** replay stream with a monotonic `sequence_number`; reconnect via `GET … ?last_event_id=N`. |
| **Human-in-the-loop (HITL)** | Ask for a decision and preserve the pending question across restarts. | The model emits an elicitation request and the human answers via `POST /elicit`. The question ID and action are validated and persisted; the running turn's watchdog still applies. |

> The GitHub Copilot SDK gives you a durable, steerable **brain**. The resilient
> task gives you a self-healing, single-writer, survivable, reconnectable
> **host** for that brain. Neither layer duplicates the other.

## Architecture

```
              POST /invocations {input, mode?}          GET /invocations/{id}?last_event_id=N
                        │                                          │  (reconnectable SSE)
                        ▼                                          ▼
        ┌──────────────────────────────┐            ┌──────────────────────────┐
        │  main.py (invocations host)  │            │  file-backed replay      │
        │  start / steer / queue /     │─emit────────►  stream (survives crash) │
        │  /elicit / cancel            │            └──────────────────────────┘
        └───────────────┬──────────────┘
                        │ start(task_id)              live send(immediate|enqueue), answer_elicitation
                        ▼
        ┌──────────────────────────────┐   ctx.entry_mode=="recovered" → resume_session
        │  agent.py                    │   in_progress → no-ingress survival
        │  @multi_turn_task(steerable) │   FoundryStateStore → durable elicitation marker
        └───────────────┬──────────────┘
                        │ create/resume, send, abort, on_elicitation_request
                        ▼
        ┌──────────────────────────────┐
        │  copilot_session.py harness  │  ── spawns ──►  Copilot CLI subprocess (the brain)
        └──────────────────────────────┘
```

- **One durable Copilot session per Foundry session.** `task_id = "copilot-<session_id>"`; the Copilot session id equals the Foundry session id, so `resume_session` continues the same conversation across turns and across crashes.
- **Steering / queueing bypass the framework steering queue on purpose.** Copilot supports graceful intra-turn redirection natively, so the HTTP layer sends directly to the live session; `task.start()` is used only to begin a turn or resume the conversation.

## Endpoints

| Method / path | Purpose |
|---|---|
| `POST /invocations` `{"input": "...", "mode": "immediate"\|"enqueue"?}` | Start (or resume) a turn; if a turn is already live, **steer** (`immediate`) or **queue** (`enqueue`) it. Returns `202` JSON, or a live SSE stream when `Accept: text/event-stream`. |
| `GET /invocations/{id}` (`Accept: text/event-stream`, optional `?last_event_id=N`) | Reconnectable SSE; the file-backed replay serves the gap after a drop/crash before live-tailing. |
| `GET /invocations/{id}` (no SSE header) | Invocation-scoped JSON status/result; earlier IDs do not report a later turn's state. |
| `POST /elicit?agent_session_id=<sid>` `{"session_id","elicitation_id","action","content"?}` | Answer a human-in-the-loop pause. Body session must match the resolved caller/hosted session; a mismatch is rejected. |
| `POST /invocations/{id}/cancel` | Abort the specified active invocation, not a later turn in the same session. |

## Environment Variables

This agent supports two LLM backends:

| Variable | Required | Description |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | For Foundry hosting | Foundry project endpoint. Auto-injected when hosted; set locally for local runs. Also the default model endpoint. |
| `AZURE_AI_MODEL_ENDPOINT` | No | Optional model endpoint override when the model is in another Foundry project. Does not change the State Store/hosting project; the identity needs inference access to that model resource. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | For Foundry model | Model deployment name (e.g. `gpt-5.4-mini`). |
| `GITHUB_TOKEN` | For Copilot model | GitHub fine-grained PAT with **Copilot Requests → Read-only**. |
| `SIMULATE_CRASH_AFTER_EVENTS` | No | Local crash-recovery testing hook (see below). |

- Foundry model set → **BYOK via Managed Identity** (no token). Copilot model set → uses `GITHUB_TOKEN`. Both set → **Foundry wins**.

The model deployment must support the Responses API. Model hosting can be in a
different region/project from the hosted agent; use the endpoint override rather
than replacing the platform-provided `FOUNDRY_PROJECT_ENDPOINT`.

## Run it locally

```bash
cd src/resilient-copilot
uv sync --frozen    # creates .venv from the committed dependency lock
az login   # for the BYOK Foundry-model path (Managed Identity)
cp .env.example .env  # then edit
uv run --frozen python main.py   # listens on http://localhost:8088
```

On native Windows, keep `AGENTSERVER_STATE_ROOT` short if the CLI reports
`unable to open database file`: session-directory names and SQLite WAL/SHM
suffixes can push a long root beyond the native SQLite path limit. For example:

```powershell
$env:AGENTSERVER_STATE_ROOT = Join-Path $env:TEMP 'copilot-state'
```

The `input_id` field is optional. Supply a stable ID when retrying a native
follow-up so the persisted receipt can identify the same request. An ID is
generated only when the field is absent; explicit empty or non-string values
are rejected. Reusing an ID with a different prompt or mode is rejected even
while the original input is still accepted but not delivered. The unfinished-input
journal is bounded to 32 entries and 512 KiB of JSON; wait for work to finish before
submitting more when that bound is reached.

The initial input is journaled before the harness becomes ready. Copilot creates
its workspace database lazily, so an early delivery receipt is not a session
snapshot. The first tool/final checkpoint saves the required files once present;
a crash before that checkpoint replays the durable input, not live memory.

While the harness is ready, `immediate` and `enqueue` use Copilot's native
controls. During startup, follow-ups wait for readiness. A request arriving
after the harness enters closing becomes a durable next turn; it cannot
redirect a turn that has already ended.

### 1) Stream a turn (with reconnect)

```bash
# Start a background+store+stream turn and watch it live:
curl -N -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" -H "Accept: text/event-stream" \
  -d '{"input": "Research the tradeoffs of async vs threads in Python, step by step."}'
```

Note the `sequence_number` on the last event you received, then reconnect and
resume with **no gap**:

```bash
curl -N "http://localhost:8088/invocations/<invocation_id>?last_event_id=<N>" \
  -H "Accept: text/event-stream"
```

### 2) Steer or queue the live turn

While a turn is running, send a second request on the **same session**:

```bash
# Redirect the current turn immediately:
curl -X POST "http://localhost:8088/invocations?agent_session_id=<sid>" \
  -H "Content-Type: application/json" \
  -d '{"input": "Actually, focus only on asyncio.", "mode": "immediate"}'

# Or queue a follow-up to run after it finishes:
curl -X POST "http://localhost:8088/invocations?agent_session_id=<sid>" \
  -H "Content-Type: application/json" \
  -d '{"input": "Then summarize in 3 bullets.", "mode": "enqueue"}'
```

### 3) Answer a human-in-the-loop pause

When the model raises an elicitation, the stream carries an
`elicitation_request` event with an `elicitation_id`. Answer it:

```bash
curl -X POST "http://localhost:8088/elicit?agent_session_id=<sid>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<sid>", "elicitation_id": "<eid>", "action": "accept", "content": {"approved": true}}'
```

The request's resolved session and the body `session_id` must agree. The custom
route uses the host's configured session when present; local callers supply
`agent_session_id`. A body ID cannot select another session or substitute for
missing caller context.

## Testing crash recovery

Set `SIMULATE_CRASH_AFTER_EVENTS=N` and start a streaming turn. The process
**hard-crashes** (`os._exit(1)`) right after the Nth event is written to the replay stream —
identical, from the task's perspective, to a SIGKILL/OOM. On restart the
framework re-invokes the task with `entry_mode="recovered"`, calls
`resume_session`, emits a `recovered` marker, and continues on the **same**
file-backed stream, so a client reconnecting via `?last_event_id=N` sees the
pre-crash events + `recovered` + the continuation.

### Todo checkpoint boundaries

Multiple todos can complete in one Copilot turn. Completing a todo does not
end the turn or create another Foundry task. This sample preserves that behavior
and saves the session after each detected todo/plan or declared required-file
change.

The pinned CLI stores todos in the session workspace's `session.db`. The
post-tool hook compares the `todos` and `todo_deps` rows, `plan.md`, and declared
required files with the last acknowledged state. Read-only queries do not
create another snapshot.
The task handles the checkpoint in its own request context and acknowledges the
hook only after saving the snapshot and marker. Detection and persistence
failures reach the task consumer and fail the turn rather than claiming
progress was saved; SDK hook-error suppression is not treated as success.

Live snapshots use SQLite's online backup API, so committed todo rows in an
active WAL are included without copying active database sidecars. The final
checkpoint uses this path too, even after requesting CLI shutdown, because a
failed stop may leave a writer running. An incomplete
JSONL tail is omitted. Symbolic links are excluded before any file is read,
so they cannot add out-of-tree data or unrestorable link members.
Each database is consistent independently; this is not an atomic snapshot
across all files or an exactly-once guarantee for tool effects.
Recovery re-drives the prompt with the saved plan, rather than resuming a live
instruction pointer.

### Required-only session snapshot

The sample keeps one archive per session in `copilot-session-snapshots-v2`.
New snapshots contain only the core CLI files needed for continuation:

- `session-store.db` and `session-state/<session_id>/session.db`, including
  todo/dependency state.
- The session's `events.jsonl`, `workspace.yaml`, `checkpoints/index.md` and
  `plan.md`, when present.
- The required-file declaration and files it explicitly selects, when present.

Optional generated outputs, caches, downloads and diagnostic logs remain on
the runtime filesystem. They are not promised to survive container replacement.
No persistent disk or extra storage resource is provisioned by this sample.
Copilot's `events.jsonl` is recovery history, not an optional diagnostic log.

To preserve an artifact, create
`session-state/<session_id>/continuation-files.json` under that session's
Copilot configuration directory:

```json
{
  "schema": "copilot-continuation-files/v1",
  "paths": ["artifacts/continuation.txt", "outputs/approved-state.json"]
}
```

Paths refer to regular files inside `session-state/<session_id>`, use `/`
separators and cannot be absolute, duplicated, traversal paths or symlinks.
Missing/invalid declared files fail the checkpoint. A file's location or
extension alone does not make it required. Tell the agent to create this
declaration when unfinished work depends on generated files. Files outside
the session workspace, including `/tmp`, need separate durable storage.
Removing a declaration deliberately removes those artifacts from future
snapshots. Registered executable files retain their permissions.

The selected files are packed into one archive and written as one State Store
value. Packing/validation failures happen before that write, leaving the
previous snapshot intact. No cross-store manifest or category protocol is
needed.

The latest checkpoint is also saved at the turn boundary. Hosted writes use
platform State Store; offline mode atomically replaces a local archive.
Retention is 30 days from the last snapshot write, separate from task retention.
Existing v2 and legacy v1 archives remain readable, including their previously
saved artifacts. The next new snapshot applies the required-only selection.
Expired legacy data cannot be recovered by changing the newer store's TTL.

The serialized snapshot value is bounded at 5 MiB, including base64 and JSON
overhead. The task attachment API's 10 MiB limit is a different limit.
Values above 1 MiB require the service's managed value offload; that path stores
the value through Dataset-backed blob storage and hydrates it on reads. With
offload disabled, the service can reject values above 1 MiB. No additional
Blob Storage resource is created by this sample, and oversized or rejected
snapshots fail explicitly.

Run the focused tests from the sample root:

```bash
uv run --frozen --project src/resilient-copilot python -m unittest discover -s tests -v
```

> **Why `os._exit` and not a "simulate shutdown" flag?** Crash recovery is the
> lease-expiry path and must be exercised with a real abrupt exit. A handler
> cannot fake a *graceful* shutdown by setting the context's shutdown event —
> `exit_for_recovery()` validates the framework-owned shutdown signal, so a
> self-set shutdown raises at the call site. Use a real `SIGTERM` for graceful
> shutdown and `os._exit`/SIGKILL for crash.

> **Local OS note.** The framework's stream lock self-heals on process death on
> Linux/WSL (kernel-released `flock`). On native Windows the best-effort lock
> file can be left behind by a hard kill; if a local restart can't re-open a
> stream, delete `"$env:AGENTSERVER_STATE_ROOT"/streams/*.lock` between the
> crash and the restart. Hosted (Linux) deployments are unaffected.

## The HITL + crash caveat (be precise)

A human-in-the-loop pause spans four pieces of state: the durable task, the
durable stream, the **live Copilot subprocess** (holding the pending
elicitation), and an in-memory Future in this host.

- **No client traffic does not itself end an active turn.** The task holds
  `in_progress` while the model waits on an elicitation. The turn watchdog and
  platform lifecycle still apply; this is not an unlimited durable human wait.
- **A hard crash while parked on an elicitation** kills the live subprocess and
  the in-memory Future. On recovery `resume_session` restores the conversation
  and stream, and this sample re-surfaces the pending question from the durable
  `FoundryStateStore` marker so the client is told "still waiting on you." If the
  Copilot CLI does not itself re-broadcast the pending elicitation on resume,
  answering it validates the stored question ID and delivers the human's action
  and optional content to the resumed session as a structured message. Delivery
  is at-least-once across a crash, not an exactly-once effect guarantee — worst
  case the human answers once more.

## Deploy to Foundry

```bash
azd ext install microsoft.foundry       # one-time
azd auth login
azd provision   # Foundry project + Container Registry + gpt-5.4-mini deployment
azd deploy      # remote ACR build → agent version
azd ai agent invoke '{"input": "Hi, what can you do?"}'
```

## Related samples

- [github-copilot](../github-copilot) — the minimal GitHub Copilot SDK getting-started agent (invocations, streaming SSE).
- [resilient-research](../resilient-research) — the same resilient primitives with a synthetic long-running research brain (crash recovery + steering + streaming reconnect).
