# GHCP Long-Running Agent Sample — Design & Investigation

> Living document for this session/topic. Appended to as work progresses.
> Last updated: 2026-08-11T16:40 (+05:30)

## Summary

We are designing a **new "long-running agent" sample** for the **GitHub Copilot SDK
(ghcp)** in the `microsoft-foundry/foundry-samples` repo. Unlike our earlier
resilient samples (which use a *simulated* brain), this one uses the **real GitHub
Copilot SDK** (`copilot` v0.1.0, bundled `copilot.exe` CLI subprocess) as the agent
brain, wrapped in the Foundry **resilient `@task`** hosting envelope. The user chose the
**full showcase + HITL** capability set. A detailed HITL-vs-crash caveat has been
analysed. Auth for a live end-to-end test is still pending (need a Foundry
endpoint+model or a GitHub PAT). No sample code written yet — design/approval phase.

---

## Timeline

| When | Event / Finding |
|------|-----------------|
| Earlier session | Built & merged resilient samples: resilient-approval-gate (#846), resilient-research (#847), resilient-steering (#850); bump PR #899 (draft). |
| This session | Opened **PR #905** (resilient-streaming, responses) — all CI green, marked ready. |
| This session | Explained the `sample_19`/`sample_20` `SIMULATE_SHUTDOWN_MS` bug (sets responses-leaf `context.shutdown`, not core `ctx.shutdown`) and the correct fix. |
| This session | Confirmed the customer's linked MAF `main.py` is clean; their RuntimeError came from a temporary `context.shutdown.set()` hack (same defect as the SDK sample). |
| This session | Surveyed existing **ghcp samples** (2): `activity/github-copilot` (Teams assistant, `.ci-skip`) and `invocations/github-copilot` (minimal SSE, runs in CI via test-payload). |
| This session | Inspected the **Copilot SDK surface**; found native steering/queueing/HITL/infinite-sessions/durable-resume primitives. |
| This session | User chose **full showcase + HITL**. Produced folder layout + capability-mapping design. |
| This session | Deep-dived the **HITL + hard-crash caveat** (four state layers; idle-eviction safe vs hard-crash lossy; one SDK-internal unknown). |

---

## Key SDK facts (verified statically)

### GitHub Copilot SDK (`copilot` v0.1.0)
- Installed at `C:\Users\namantyagi\AppData\Roaming\Python\Python314\site-packages\copilot`.
- Ships a **bundled CLI**: `copilot/bin/copilot.exe` (~113 MB, VERSION 6). `CopilotClient.start()`
  spawns it locally; `SubprocessConfig(cli_path=..., github_token=...)` overrides. `_get_bundled_cli_path()`
  returns the bundled path when `cli_path is None`.
- `CopilotClient` methods: `start/stop/force_stop`, `create_session`, `resume_session`,
  `list_sessions`, `get_session_metadata`, `delete_session`, `get_auth_status`,
  `get/set_foreground_session_id`, `get_last_session_id`, `list_models`, `ping`, `on`, `rpc`.
- `CopilotSession` methods: `send`, `send_and_wait`, `abort`, `get_messages`, `set_model`,
  `on`, `ui`, `rpc`, `capabilities`, `destroy`, `disconnect`, `log`, `workspace_path`.

### Native capability primitives
| Capability | Copilot SDK API |
|---|---|
| Steering | `session.send(prompt, mode="immediate")` |
| Queueing | `session.send(prompt, mode="enqueue")` |
| Abort | `session.abort()` |
| Infinite / long-running | `infinite_sessions=InfiniteSessionConfig(enabled, background_compaction_threshold, buffer_exhaustion_threshold)` → auto context-compaction + workspace persistence |
| Durable session + resume | `create_session(session_id=...)`, `resume_session(id)`, `list_sessions`, `get_session_metadata` |
| HITL | `on_elicitation_request` callback (JSON-schema form → `ElicitationResult(action=accept/decline/cancel, content)`); also `on_user_input_request`, `on_permission_request` |
| Session multiplexing | `get/set_foreground_session_id` |
| Extensibility | `define_tool`, `mcp_servers`, `skill_directories`, `commands`, `custom_agents`, `hooks` |

- `send(prompt, *, attachments=None, mode: Literal["enqueue","immediate"]|None=None) -> str` (returns messageId).
- `send_and_wait(..., timeout=60.0)` — blocks until assistant finishes; timeout does NOT abort in-flight work.

### Elicitation (HITL) mechanics
- `create/resume_session(..., on_elicitation_request=ElicitationHandler)`; sets `payload["requestElicitation"]=True`.
- `ElicitationHandler = Callable[[ElicitationContext], ElicitationResult | Awaitable[ElicitationResult]]`.
- `ElicitationContext`: `session_id, message, requestedSchema, mode("form"|"url"), elicitationSource, url`.
- `ElicitationResult`: `action: "accept"|"decline"|"cancel"`, `content: dict[str, str|float|bool|list[str]]`.
- Flow (`session.py:1449-1486`): CLI broadcasts `elicitation.requested {request_id}` → handler invoked →
  respond via `rpc.ui.handle_pending_elicitation(request_id, result)`. On handler error, auto-cancels
  (`action=CANCEL`) so the server doesn't hang. **Elicitations are tracked server-side by `request_id`
  ("pending elicitation"), not merely as a client Future.**

---

## Sample design

### Folder layout (mirrors merged samples)
```
samples/python/hosted-agents/bring-your-own/invocations/resilient-copilot/
├── azure.yaml                      # Foundry provider, gpt-5-mini model, name: resilient-copilot
├── README.md                       # capabilities + walkthroughs + HITL/crash caveat
├── AGENTS.md  CLAUDE.md
└── src/resilient-copilot/
    ├── main.py                     # HTTP surface: POST / GET-SSE / elicit / cancel
    ├── agent.py                    # the resilient @task: owns Copilot session lifecycle
    ├── copilot_session.py          # Copilot SDK harness (create/resume, event pump, elicit bridge)
    ├── pyproject.toml, uv.lock, uv.toml   # azure-ai-agentserver-invocations, github-copilot-sdk, azure-identity
    ├── Dockerfile  .env.example  .dockerignore  .azdignore
internal/tools/samples-hosted-agents/python/bring-your-own/invocations/resilient-copilot/test-spec.yml
```

### Capability mapping
- One durable Copilot session per Foundry session: `task_id = f"copilot-{session_id}"`; Copilot `session_id` == Foundry `session_id`. Resilient `@multi_turn_task(steerable=True)` owns the session lifecycle.
- **Long-running / no-ingress survival**: task stays `in_progress`; Copilot session stays live with zero traffic.
- **Crash recovery**: on `ctx.entry_mode == "recovered"` → `resume_session(session_id)` (workspace persisted to disk) instead of `create_session`; emit `recovered` marker; continue pumping.
- **Steering**: POST while running → `send(prompt, mode="immediate")`.
- **Queueing**: POST `{"mode":"enqueue"}` → `send(prompt, mode="enqueue")`.
- **Streaming w/ reconnect**: each Copilot `SessionEvent` → `stream.emit(event.to_dict())` on file-backed replay stream; GET-SSE with `?last_event_id=N` cursor (`streams.use_file_backed_replay`).
- **HITL**: `on_elicitation_request` → emit `elicitation_request` event (id + schema) into stream + park `asyncio.Future`; client answers via `POST /invocations/{id}/elicit`; resolve Future → callback returns `ElicitationResult` → Copilot continues.

### HTTP surface (invocations protocol)
- `POST /invocations` `{"input","mode":"immediate|enqueue"}` → start (first) / steer / queue; `202 {invocation_id, session_id}` or live SSE if `Accept: text/event-stream`.
- `GET /invocations/{id}` + SSE + optional `?last_event_id=N` → reconnectable stream; without header → JSON snapshot.
- `POST /invocations/{id}/elicit` `{"elicitation_id","action","content"}` → answer a HITL pause.
- `POST /invocations/{id}/cancel` → `session.abort()` + cooperative wind-down.

### Recovery flow
1. Container crashes mid-run → lease expires.
2. Framework re-invokes `copilot_agent` with `entry_mode="recovered"`, same `ctx.input`, same `invocation_id`.
3. Handler calls `resume_session(session_id)` → Copilot rehydrates durable workspace.
4. File-backed stream rehydrated from disk → reconnecting GET-SSE client (`?last_event_id=N`) sees pre-crash events + `recovered` marker + continuation — no gap.

---

## THE HITL + HARD-CRASH CAVEAT (detailed)

### Four layers of state during a HITL pause
1. **Foundry resilient task** (`ctx`, Python host) — durable (`AGENTSERVER_STATE_ROOT`).
2. **File-backed replay stream** — SSE history on disk (durable).
3. **Copilot CLI subprocess** (`copilot.exe`) — live agent turn: model context, in-flight tool call, pending-elicitation registry keyed by `request_id`.
4. **Elicitation bridge** — in-memory `asyncio.Future` in the Python host inside `on_elicitation_request`.

### Idle-eviction (no traffic) — fully survivable ✅
Container not killed; all four layers alive. Task holds `in_progress` (platform won't evict an active turn). Subprocess blocks on `request_id` indefinitely; whenever the human answers (minutes/hours), the Future resolves and the turn continues. Nothing lost.

### Hard crash (SIGKILL / OOM / node dies) — lossy for the in-flight elicitation ⚠️
Whole container dies → all live state dies at once:
- **Layer 4 (Future)** — gone (pure process memory).
- **Layer 3 (CLI subprocess + its pending registry)** — gone.

On recovery: fresh container, `entry_mode="recovered"`, `resume_session(session_id)` spawns a NEW `copilot.exe` and rehydrates the durable workspace.

**Reliably recovers:** Layer 1 (task, same invocation_id/input); Layer 2 (stream; `?last_event_id=N` sees pre-crash events + `recovered` + continuation); the conversation up to the crash (completed turns + workspace).

**At risk — the specific in-flight elicitation:** depends on ONE SDK-internal unknown: *does the CLI persist a pending elicitation to the durable workspace and re-broadcast `elicitation.requested` on resume?*
- If yes → in-flight elicitation also recovers (HITL fully crash-safe).
- If no (more likely — in-flight tool calls are live turn state, not checkpointed) → the interrupted turn's question is dropped; durable session intact but that "waiting for approval" moment evaporates; client must re-issue.

Same class of boundary as resilient-research: committed-before-checkpoint recovers; in-flight-at-crash re-runs. An un-answered elicitation is in-flight-at-crash state.

### How the sample stays correct either way (crash-aware, idempotent bridge)
1. Persist a pending-elicitation marker to an explicit `FoundryStateStore` when parking a Future: `{elicitation_id, request_id, message, schema, status:"pending"}`.
2. On `recovered` entry, read the marker and re-emit an `elicitation_request` event so reconnecting clients are told "still waiting on you."
3. When the client answers, if the live CLI `request_id` is gone (post-crash), fall back to feeding the answer as a normal `session.send(...)`, then clear the marker.
4. Timeout/no-answer → resolve `action="cancel"` so nothing hangs (mirrors SDK auto-cancel at `session.py:1475`).

Net: idle-eviction transparently survivable; hard crash never hangs, never silently drops the human's decision (worst case: one re-answer).

### To verify during the live test
Empirically test whether `resume_session` re-broadcasts a pending elicitation: park on an elicitation → `os._exit(1)` → restart → watch for a re-emitted `elicitation.requested`. Design is correct either way; the test only tells us whether the step 2/3 fallback ever fires.

---

## Environment / testing notes
- Bundled `copilot.exe` present and `start()` works locally.
- **No** `GITHUB_TOKEN`, **no** `FOUNDRY_PROJECT_ENDPOINT`/`AZURE_AI_MODEL_DEPLOYMENT_NAME` currently set.
- `az login` active: `namantyagi@microsoft.com`, sub `azure-openai-agents-exp-nonprod-01`.
- BYOK local run needs a Foundry project endpoint + model deployment; Copilot-model run needs a fine-grained PAT (`github_pat_`, Copilot Requests: Read-only).
- Existing ghcp invocations sample runs in Cloud E2E via `test-payload.txt` (NOT `.ci-skip`); the activity ghcp sample IS `.ci-skip`.
- New hosted-agent samples require a `test-spec.yml` under `internal/tools/samples-hosted-agents/...`.

## Open decisions / next steps
- [ ] **Decision:** one comprehensive `resilient-copilot` (5 caps + HITL) vs split HITL into a second sample.
- [ ] **Auth:** obtain Foundry endpoint+model or GitHub PAT for the live end-to-end test.
- [ ] Build the sample (main.py, agent.py, copilot_session.py, azure.yaml, README, AGENTS/CLAUDE, Dockerfile, env, test-spec).
- [ ] Verify offline (structure) then live (streaming, steering, queueing, elicitation round-trip, crash→resume).
- [ ] Open draft PR; pass CI (Cloud E2E, contract policy, mailmap).

## How the resilient `@task` primitive is used (added 2026-08-11T19:12)

**Core decision:** there are TWO turn/steering models — the Foundry task's and the
Copilot SDK's. We use the Foundry `@multi_turn_task` as the **durable supervisor of the
whole Copilot session's life**, NOT as a per-message turn driver. Copilot's own
`send(immediate/enqueue)` drives steering/queueing, so the ghcp-native controls are
what's showcased (not buried under the framework steering queue).

Task body sketch:
```python
@multi_turn_task(name="copilot_agent", steerable=True)
async def copilot_agent(ctx: TaskContext[dict]) -> None:
    session_id = ctx.input["session_id"]; inv_id = ctx.input["invocation_id"]
    stream = await streams.get_or_create(inv_id)
    if ctx.entry_mode == "recovered":
        session = await harness.resume_session(session_id, on_elicit=...)
        await emit(stream, {"type":"recovered","recovery_count":ctx.recovery_count})
        if state.get("pending_elicitation"):
            await emit(stream, {"type":"elicitation_request", **state["pending_elicitation"]})
    else:
        session = await harness.create_session(session_id, on_elicit=...)
    registry[session_id] = session
    await session.send(ctx.input["prompt"])
    async for ev in harness.events(session):
        if ctx.cancel.is_set() or ctx.shutdown.is_set(): break
        await emit(stream, ev.to_dict())
        if ev.type == SESSION_IDLE and harness.queue_empty(session): break
```

`ctx` surfaces used:
- `@multi_turn_task(steerable=True)` — durable recoverable multi-turn chain, one per session; concurrent `start()` queues instead of raising `TaskConflictError`.
- **in_progress while body runs** = no-ingress survival (platform won't idle-evict an active turn) — this IS "long-running."
- `ctx.entry_mode == "recovered"` = crash-recovery hook → `resume_session()` + `recovered` marker.
- `ctx.recovery_count` — surfaced in the recovered marker.
- `FoundryStateStore` — durable application state surviving crash; holds the pending-elicitation marker and snapshot reference.
- `ctx.cancel` — operator cancel (`run.cancel()`); loop winds down + `session.abort()`.
- `ctx.shutdown` — real SIGTERM → clean break; optional `exit_for_recovery()` for next-lifetime resumption.
- `ctx.input` / `ctx.input_id` — `{prompt, session_id, invocation_id, call_id}`; preserved verbatim on recovered re-entry.

**Deviation & rationale:** steering/queueing go DIRECTLY to the live Copilot session, not the framework steering queue:
```python
run = await get_task_manager().get_active_run(task_id)
if run is not None:
    await registry[session_id].send(prompt, mode="immediate")  # steer (or "enqueue" = queue)
else:
    await copilot_agent.start(task_id, input={...})            # first turn / post-idle new turn
```
Research-style steer cancels+re-enters (restart phases); here the live Copilot agent supports graceful intra-turn redirect (`immediate`) + post-turn `enqueue` natively — routing through cancel-and-re-enter would throw those away. So `start()` only CREATES the task (first turn) or RE-STARTS after idle/suspend; live follow-ups go to `session.send()`.

**Net — the task primitive provides exactly 3 things:** (1) survival (in_progress keeps a client-less Copilot turn alive), (2) recovery (recovered entry → resume_session + durable metadata incl. elicitation marker), (3) identity+lifecycle (one durable task_id/session, cooperative cancel/shutdown, preserved input). Everything conversational rides on the Copilot session the task supervises.

Verified task API (core `tasks/`): `@task` (one-shot; rejects `steerable=`/`ephemeral=`) vs `@multi_turn_task(name=, steerable=False, ...)`. `TaskContext` attrs: `task_id, input_id, input, metadata, recovery_count, cancel, shutdown, entry_mode, cancel_requested, is_steered_turn, pending_input_count, timeout_exceeded`. `exit_for_recovery()` guards on `ctx.shutdown.is_set()` (core event). Cancel watchdog sets `ctx.cancel` but does NOT force-stop the handler (cooperative wind-down).

## What the resilient `@task` adds OVER the Copilot SDK (added 2026-08-11T19:37)

Copilot persists+resumes a session, but resumption is a PULL op: something alive must call
`resume_session` on the right node exactly once. The task makes that safe & automatic.

| # | Extra the task provides | Why Copilot alone can't |
|---|---|---|
| 1 | **Automatic crash re-invocation** — recovery scan re-enters handler with `entry_mode="recovered"` (the thing that calls `resume_session`). | Copilot only persists to disk; nobody triggers resume after a crash. Library, not supervisor. |
| 2 | **No-ingress survival / eviction control** — `in_progress` keeps the container alive for a long client-less turn. | Durable-on-disk session doesn't stop Foundry idle-eviction; Copilot has no eviction lever. |
| 3 | **Lease / single-writer safety** — `lease_owner`, `lease_instance_id`, `lease_duration_seconds`, `lease_held_by_another`, `lease_expired`; crashed owner's lease expires, exactly one replacement reclaims. | Copilot workspace has no distributed lease; two nodes resuming same session = split-brain/corruption. |
| 4 | **Managed reconnectable SSE** — file-backed replay + `?last_event_id=N` serves the gap after a drop/crash. | Copilot events go to an in-process callback; no durable HTTP event log, disconnect = lost events. |
| 5 | **Hosted protocol surface** — invocations/responses REST endpoint, platform headers, session resolution, health probes, OTel. | Copilot is a local JSON-RPC subprocess, not a Foundry HTTP agent endpoint. |
| 6 | **Durable app-level metadata** — an explicit `FoundryStateStore` item holds the pending-elicitation marker and snapshot reference across crashes. | Copilot persists the conversation, not arbitrary hosted-task checkpoints keyed to the run. |
| 7 | **Cooperative cancel/timeout w/ grace** — watchdog sets `ctx.cancel` + grace window without force-kill; `entry_mode`/`recovery_count`/`is_steered_turn` branch fresh-vs-recovered-vs-steered. | Copilot `abort()` cancels a turn but has no hosted timeout/grace and doesn't tell you why you're running. |

One-liner: **Copilot = durable steerable brain; task = durable, self-healing, single-writer, survivable, reconnectable HOST for that brain.** Clean division: Copilot owns the conversation (memory, steering, queueing, HITL); task owns durability, survival, recovery, coordination, hosted stream. No duplication.

## DECISION LOG
- 2026-08-11T19:37 — **Building now.** User approved starting implementation. (Split-vs-single still to confirm during build; defaulting to ONE comprehensive `resilient-copilot` unless told otherwise.)

## VERSION / IMPORT FINDINGS (2026-08-11T19:42) — IMPORTANT
- Installed: `azure-ai-agentserver-core==2.0.0b11`, `azure-ai-agentserver-invocations==1.0.0b8`, `github-copilot-sdk==0.2.1` (bundled CLI VERSION 1.0.17).
- **`github-copilot-sdk` 0.2.1 moved symbols out of top-level `copilot`.** Correct 0.2.1 paths:
  - `from copilot import CopilotClient`
  - `from copilot.session import PermissionHandler, ProviderConfig`
  - `from copilot.generated.session_events import SessionEventType, SessionEvent`
- **The MERGED ghcp invocations sample is likely BROKEN on 0.2.1** — it does `from copilot import PermissionHandler, ProviderConfig` and `from copilot.session_events import SessionEventType`, which no longer resolve. (Worth reporting/fixing separately; our new sample must use the submodule paths, ideally with a defensive try/except fallback for 0.2.0.)
- `ProviderConfig` keys: `type, wire_api, base_url, api_key, bearer_token, azure`.
- Key `SessionEventType` values we use: `SESSION_IDLE` (turn done/agent idle), `SESSION_ERROR`, `ELICITATION_REQUESTED`/`ELICITATION_COMPLETED`, `ASSISTANT_MESSAGE`/`ASSISTANT_MESSAGE_DELTA`, `ASSISTANT_TURN_START`/`ASSISTANT_TURN_END`, `SESSION_RESUME`, `SESSION_SHUTDOWN`, `TOOL_EXECUTION_START`/`TOOL_EXECUTION_COMPLETE`.
- `InvocationAgentServerHost` supports **`add_route`** (custom `/elicit` endpoint), plus `invoke_handler`/`get_invocation_handler`/`cancel_invocation_handler`, `mount`, `add_middleware`.
- `SessionEvent` has `.to_dict()` / `.from_dict()` / `.ephemeral` / `.parent_id`.

## BUILD LOG (2026-08-11T20:xx)
Built **resilient-copilot** (invocations) on branch `sample/resilient-copilot`. Files:
- `azure.yaml`, `README.md`, `AGENTS.md`, `CLAUDE.md`
- `src/resilient-copilot/`: `main.py`, `agent.py`, `copilot_session.py`, `pyproject.toml`, `uv.lock`, `uv.toml`, `Dockerfile`, `.env.example`, `.dockerignore`, `.azdignore`
- `internal/tools/samples-hosted-agents/python/bring-your-own/invocations/resilient-copilot/test-spec.yml` (owner namantyagi; validates + plans applicable)

Design decisions locked during build:
- **Steering/queueing bypass the framework steering queue** → delivered directly to the live Copilot session via `send(mode="immediate"|"enqueue")`, looked up through an in-process `_HARNESSES[session_id]` registry. `task.start()` only begins a turn / resumes.
- **Harness always `resume-or-create`** (`recover=True`) so Copilot conversation memory continues across turns AND crashes. `recovered` MARKER still gated on `ctx.entry_mode=="recovered"`.
- **Prompt re-driven on recovery** (Copilot history restored by resume_session; some streamed content may repeat but stream has no gap). Honest note in README.
- **Stream closed on normal completion + logical-failure paths; NOT on crash** (os._exit bypasses except → stream stays open for recovery). Matches research `_finish_turn` contract.
- **Cancel is deterministic**: in-loop `ctx.cancel/shutdown` check breaks the pump + explicit `harness.abort()` in the cancel branch (plus a watcher that aborts a *blocked* pump).
- **Crash hook = `SIMULATE_CRASH_AFTER_EVENTS` → os._exit(1)** (NOT a shutdown flag — same reasoning as sample_19 fix).
- **HITL bridge**: `on_elicitation_request` parks a Future and persists `state["pending_elicitation"]` in `FoundryStateStore`; `/elicit` resolves it, or (post-crash, no live Future) falls back to delivering the answer as a normal `session.send`.

OFFLINE VERIFICATION (drove real task body `copilot_agent._fn` with a fake harness + real file-backed streams): **ALL 4 PASSED**
- happy_path: turn_start → copilot events → turn_complete; sequence_numbers monotonic/unique; `?last_event_id=N` reconnect skips correctly; stream closed.
- recovered_redrive: `recovered` marker + re-surfaced `elicitation_request(recovered=True)` from durable metadata; `recover=True`.
- cancel_path: cancel before pump → `cancelled` + `abort()` called.
- elicitation_bridge: real `_elicitation_handler` parks Future, `answer_elicitation` resolves to `{action:accept, content:{...}}`; unknown id → False.

STILL BLOCKED: **live model run** (streaming/steer/queue/elicit/crash-resume against a real Copilot loop) needs a Foundry endpoint+model or a GitHub PAT.

NOTE TO REPORT: the merged `github-copilot` invocations sample's imports are broken on `github-copilot-sdk` 0.2.1 (top-level `PermissionHandler`/`ProviderConfig`/`session_events` moved). Our sample uses submodule paths with a 0.2.0 fallback.

## Reference file paths
- Existing ghcp: `samples/python/hosted-agents/bring-your-own/invocations/github-copilot/src/github-copilot-invocations/main.py`
- Existing ghcp Teams: `samples/.../activity/github-copilot/` (client.py/tools.py/files.py/outfiles.py/cards.py)
- Resilient pattern to mirror: `samples/.../invocations/resilient-research/src/resilient-research/{main.py,agent.py,store.py}`
- Copilot SDK source: `C:\Users\namantyagi\AppData\Roaming\Python\Python314\site-packages\copilot\{client.py,session.py,tools.py}`
