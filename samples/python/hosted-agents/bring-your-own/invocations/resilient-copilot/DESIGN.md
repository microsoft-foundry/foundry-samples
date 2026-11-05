# Resilient Copilot: architecture and recovery boundaries

## Overview

This sample runs a real GitHub Copilot SDK agent through the Foundry Invocations
protocol. The Copilot SDK owns the model-and-tool loop. An AgentServer
`@multi_turn_task` supervises that loop, supplies lease-based recovery, and
maintains a reconnectable event stream.

Dependencies are pinned in `src/resilient-copilot/pyproject.toml` and `uv.lock`.
The sample uses GitHub Copilot SDK 1.0.11, AgentServer Core 2.1.0 and
AgentServer Invocations 1.1.0. The deployment manifest uses Python 3.13 code
deployment; the Dockerfile provides a container alternative.

## Components

| Component | Responsibility |
|---|---|
| `main.py` | HTTP invocation, follow-up, elicitation and cancellation routes |
| `agent.py` | One resilient multi-turn task per Foundry session; owns durable state and event handling |
| `copilot_session.py` | Copilot session lifecycle, token acquisition, native controls, hooks and event pump |
| `store.py` | Session snapshot packing, State Store persistence and restoration |
| `tests/` | Offline regression tests for snapshot and lifecycle boundaries |

```text
Client requests
      |
      v
Invocations host -----> per-session supervision
                              |
                 +------------+------------+
                 |                         |
                 v                         v
          Copilot SDK/CLI           Foundry State Store
          model + tools             application state
                 |                 session snapshots
                 v
          file-backed events ------> reconnecting clients
```

The task and the Copilot session have related identities, but different roles:
the task records execution lifecycle; the Copilot session holds conversation
and planning state. Session identifiers must be validated and filesystem paths
confined before the SDK is started or snapshots are accessed.

## Persistence

There are three distinct persistence boundaries:

1. **Task record.** The framework retains the input and lease state needed to
   invoke the handler after a restart. A multi-turn return suspends the task;
   it does not persist the handler's returned output.
2. **Application state and session snapshot.** The sample saves its control
   state in `FoundryStateStore`. A required-only snapshot contains the CLI's
   recovery databases, conversation/configuration, plan and explicitly
   declared required artifacts. Optional outputs remain on runtime disk.
   Separate invocation-keyed records preserve
   each turn's polling status across later turns in the same session.
3. **Replay stream.** Copilot events are written to a file-backed stream with
   increasing sequence numbers. This is separate from the State Store snapshot;
   saving an event is not proof that the session snapshot was committed.

In hosted execution the State Store is platform-backed. Local execution uses
local storage fallbacks; those do not prove survival of hosted container
replacement. The full event-history guarantee also depends on retention and
preservation of the stream's backing storage.

### Todo checkpoints

Multiple todos can finish during one Copilot turn. A todo update does not create
another Foundry turn or another independently decorated task.

The pinned Copilot CLI exposes a session workspace containing `session.db`.
After a tool finishes, the sample compares committed `todos` and `todo_deps`
rows, `plan.md`, the required-file declaration and declared file contents
against the last acknowledged state. If they changed, the hook requests a
snapshot and waits for persistence acknowledgement.

The task consumer performs the write in its execution context, then emits
`todo_checkpoint`. This is important because the Copilot SDK logs hook errors
without necessarily stopping the model. The task must fail explicitly when
checkpoint detection or persistence fails; detection errors must reach the
consumer even when the SDK suppresses the hook exception.

Live snapshots use SQLite's online backup API, rather than copying active DB
and WAL files. Database sidecars and process lock files are excluded from live
archives, and incomplete JSONL tails are omitted.
The final checkpoint uses the same live-safe path; requesting CLI shutdown
does not prove that every writer actually stopped.

Only the known CLI recovery files and declared required workspace files are
stored. The declaration is
`session-state/<session_id>/continuation-files.json`, with schema
`copilot-continuation-files/v1` and an array of workspace-relative regular-file
paths. Missing, escaping or symlink paths fail explicitly. Optional outputs,
caches and diagnostics stay on runtime disk; there is no persistent-disk
guarantee. Files outside this workspace require their own durable storage.

Each SQLite database is consistent independently. The archive is not a single
transaction across all files, and it cannot make outside tool effects exactly
once.

### One required-only archive

Keep the original `copilot-session-snapshots-v2` store and its single
`tar_gz_b64` value per session. File selection changes, not the persistence
protocol: consistent database backups, recovery history/configuration, plan
state and declared continuation artifacts share one archive.

The required-file declaration and selected files must agree. A checkpoint
must not archive a changed declaration pointing at files it did not select.
Explicitly required files such as `uv.lock` are not mistaken for CLI process
locks, and executables retain their file modes.

All packing and validation completes before the one State Store write. Failure
preserves the prior saved snapshot; success acknowledges that write. Offline
mode uses the same archive with atomic local replacement. The archive format
and v2/v1 read fallback remain compatible with existing snapshots. New writes
omit unregistered optional data, even after restoring an older full archive.

Control/HITL receipts and invocation status remain in their existing stores.
There are no new category stores, multi-item manifests or generation pointers.

### Value size and retention

State Store stores JSON values inline up to 1 MiB. When subscription-scoped
value offload is enabled, the service transparently stores larger values as
managed Dataset versions backed by blobs, up to a 5 MiB serialized JSON maximum.
Reads hydrate the original JSON through the same State Store API.

The archive is compressed and base64-encoded; its JSON size, including
base64 and JSON overhead, must stay within that maximum. Task attachments
have a separate 10 MiB limit; it does not apply to State Store values.
The sample does not provision
Blob Storage or call Dataset APIs directly. A deployment with offload disabled
can reject values above 1 MiB, and values above 5 MiB require another application
storage design. Persistence failures must not be reported as completed work.

Snapshot retention must cover the task's recovery window, not merely a short
local demonstration. State Store item retention is write-sliding and separate
from task-record retention; keeping a task active does not refresh an untouched
snapshot.

## Invocation and native controls

A first invocation starts the resilient task. Follow-ups must wait for a ready
Copilot harness or be routed to a durable next-turn path when the previous
harness is closing.

Invocation status is keyed by invocation ID, separately from the reusable
session task. Polling an earlier invocation must not expose a later turn's
active status or payload merely because both turns share that task. Cancelling
a completed invocation must not cancel a newer invocation sharing its session.
Cancellation must also bind to the invocation's stored framework input identity
and task identity; checking status before a session-only lookup is insufficient
because a later turn can start between those operations.

Native `send(mode="immediate")` redirects an active Copilot turn.
`send(mode="enqueue")` submits a follow-up after the current work. These are
Copilot controls, distinct from the framework's cancellation-driven steering
queue.

An accepted HTTP response requires durable acceptance of the input, not merely
a send to the live subprocess. Accepted-input and human-decision records allow
recovery to find unfinished controls. A crash between delivery and its durable
receipt can require replay; this is at-least-once processing, not an exactly-once
message or effect guarantee.

Initial input IDs are reserved before harness readiness. Before the CLI creates
its workspace database, persist the delivery receipt in the journal without
claiming a snapshot. Post-tool/final checkpoints still require the recovery
databases. Once a snapshot exists, a missing required database is an error,
not another startup deferral.

Callers may supply a stable `input_id` for native follow-up retries. Conflicting
content for the same ID is rejected before checking its delivery status.
An absent ID is generated; an explicitly invalid value is rejected.
The unfinished-input journal is bounded
to 32 entries and 512 KiB of JSON; it is not an unbounded message queue.
Once a harness enters closing, further inputs use a framework-durable next
turn instead of being sent to the closing subprocess.

The native-send adapter uses the pinned SDK's reader-thread response callback
to separate an old queued idle notification from completion of newly submitted
work. This is a version-specific integration covered by ordering tests; keep
the dependency lock and those tests together when upgrading the SDK.

SDK reader-thread callbacks are marshalled onto the harness's owning event
loop before touching its asyncio queue. Cancelling a send also cancels and
awaits its outstanding receiver; an item dequeued concurrently must be retained
in order, not discarded during cleanup.

## Human in the loop

The elicitation callback records the pending question and exposes it to the
client. Live responses resolve a pending Copilot Future. After a crash that
Future is gone, so the sample must validate the reply against the durable
question ID and preserve its action and optional content.

`accept` with empty content, `decline` and `cancel` are valid decisions.
Before routing, validate the body session against the request's resolved
session. The custom `/elicit` route binds to the configured hosted session, or
the local `agent_session_id` query parameter when no host session is configured;
body data cannot override this binding.
Unknown or stale question IDs must not be injected into another question's
conversation. A recovered decision can be delivered as a structured message
when the original Future no longer exists; the question may be asked again.

Completing an in-memory Future is not proof that the CLI durably consumed a
decision. Keep the accepted decision replayable until a valid session idle
boundary. An unrelated todo checkpoint does not confirm a decision. Question
updates must be serialized, and completing one decision must not erase a
different pending question.

An identical retry of a submitted decision returns its existing receipt rather
than delivering another message. A conflicting action or content for that
question is rejected before modifying the accepted decision.

The per-turn watchdog remains applicable while the handler is running or
parked on an elicitation. The sample is not an unlimited human-wait workflow
engine.

## Recovery

When the framework invokes an interrupted task as `recovered`, the handler
reloads its application state and restores the latest snapshot before opening
the Copilot session. Restoration is also needed on a later `resumed` turn when
the local session directory is absent after compute replacement.

If saved state promises a snapshot and it cannot be restored, fail explicitly.
Do not silently create a new conversation after an authentication, network,
SDK or corrupt-state resumption error.

Recovering an accepted input can repeat a delivery. Completed external actions
need a destination idempotency key or another application-level deduplication
mechanism. Neither a stable task ID nor a snapshot supplies exactly-once effects.

## Cancellation, shutdown and errors

Explicit client cancellation winds down the current work without requesting
automatic recovery. Graceful process shutdown is different: save state and
defer through `ctx.exit_for_recovery()` before terminating the replay stream.
`TaskDeferred` is not a normal handler failure.

The cancellation/shutdown watcher and its child waiters must be cancelled and
awaited when a turn ends. A Copilot `session.error` is terminal even if no idle
event follows.

The crash-simulation hook exercises a hard process exit. It must not fire again
on recovered entry merely because the resumed stream cursor exceeds its
configured threshold.

## Authentication

With a Foundry model configured, the Copilot provider obtains audience-scoped
tokens through Azure credentials. Long turns need token acquisition on demand,
rather than one bearer token fixed for the whole session. The GitHub backend
uses the configured GitHub token.

An optional model endpoint override must not replace the hosting project's
State Store binding. Cross-resource models require inference authorization for
the hosted identity.

Credentials are not snapshot contents. New token acquisition remains subject
to current identity configuration and permissions. This demonstration
auto-approves tool permissions and should only receive trusted requests.

## Validation boundaries

Offline tests exercise WAL-safe snapshots, fresh-directory restore,
acknowledgement and failure handling. Real local Copilot tests can demonstrate
todo checkpoints and session resumption using a live model.

Those results do not establish hosted State Store writes, managed-identity
authorization, Linux container replacement or platform recovery. Those require
separate deployed-agent tests. Run the commands in README; do not substitute
historical investigation logs for current validation.
