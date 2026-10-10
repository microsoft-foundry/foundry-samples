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
| **Crash recovery** | A restarted container resumes the conversation from disk. | On `ctx.entry_mode == "recovered"` the task calls `resume_session(session_id)` (the Copilot CLI persisted the session workspace) and re-drives the turn, emitting a `recovered` marker onto the same stream. |
| **Steering** | A new input redirects the in-flight turn instead of racing it. | `POST` with `{"mode":"immediate"}` while a turn is active → `session.send(prompt, mode="immediate")` on the live Copilot session. |
| **Queueing** | A follow-up input runs after the current turn. | `POST` with `{"mode":"enqueue"}` → `session.send(prompt, mode="enqueue")`. |
| **Streaming with reconnect** | Clients reconnect after a drop or crash with no gap. | Every Copilot `SessionEvent` is emitted onto a **file-backed** replay stream with a monotonic `sequence_number`; reconnect via `GET … ?last_event_id=N`. |
| **Human-in-the-loop (HITL)** | Pause indefinitely for approval, resume on the human's reply. | The model's `on_elicitation_request` parks a Future and emits an `elicitation_request` event; the human answers via `POST /elicit`; a durable marker in `FoundryStateStore` makes the pause re-drivable after a crash. |

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
| `GET /invocations/{id}` (no SSE header) | JSON snapshot of the task status / metadata. |
| `POST /elicit` `{"session_id","elicitation_id","action","content"?}` | Answer a human-in-the-loop pause (`action`: `accept`\|`decline`\|`cancel`). |
| `POST /invocations/{id}/cancel` | Abort the in-flight Copilot turn and wind the task down. |

## Environment Variables

This agent supports two LLM backends (same selection logic as the
[github-copilot](../github-copilot) getting-started sample):

| Variable | Required | Description |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | For Foundry model | Azure AI Foundry project endpoint. Auto-injected when hosted; set locally for local runs. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | For Foundry model | Model deployment name (e.g. `gpt-5.4-mini`). |
| `GITHUB_TOKEN` | For Copilot model | GitHub fine-grained PAT with **Copilot Requests → Read-only**. |
| `SIMULATE_CRASH_AFTER_EVENTS` | No | Local crash-recovery testing hook (see below). |

- Foundry model set → **BYOK via Managed Identity** (no token). Copilot model set → uses `GITHUB_TOKEN`. Both set → **Foundry wins**.

## Run it locally

```bash
cd src/resilient-copilot
uv sync            # creates .venv from pyproject.toml and uv.lock
az login   # for the BYOK Foundry-model path (Managed Identity)
cp .env.example .env  # then edit
uv run python main.py   # listens on http://localhost:8088
```

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
curl -X POST http://localhost:8088/elicit \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<sid>", "elicitation_id": "<eid>", "action": "accept", "content": {"approved": true}}'
```

## Testing crash recovery

Set `SIMULATE_CRASH_AFTER_EVENTS=N` and start a streaming turn. The process
**hard-crashes** (`os._exit(1)`) right after the Nth event is checkpointed —
identical, from the task's perspective, to a SIGKILL/OOM. On restart the
framework re-invokes the task with `entry_mode="recovered"`, calls
`resume_session`, emits a `recovered` marker, and continues on the **same**
file-backed stream, so a client reconnecting via `?last_event_id=N` sees the
pre-crash events + `recovered` + the continuation.

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

- **Idle-eviction (no traffic) is fully survivable.** The container is not
  killed; the task holds `in_progress`; the model waits on the pending
  elicitation indefinitely. Whenever the human answers — minutes or hours
  later — the turn continues. Nothing is lost.
- **A hard crash while parked on an elicitation** kills the live subprocess and
  the in-memory Future. On recovery `resume_session` restores the conversation
  and stream, and this sample re-surfaces the pending question from the durable
  `FoundryStateStore` marker so the client is told "still waiting on you." If the
  Copilot CLI does not itself re-broadcast the pending elicitation on resume,
  answering it delivers the human's decision to the resumed session as a normal
  message (via `/elicit`'s fallback) so it is never silently dropped — worst
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
