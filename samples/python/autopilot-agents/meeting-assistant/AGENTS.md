# Meeting Assistant Autopilot

These instructions apply only to this sample, not to other Autopilot samples.

## Meeting documentation maintenance

Spell out Autopilot and ActivityProtocol in documentation; do not abbreviate either.

Keep [MEETING_OBJECTS.md](MEETING_OBJECTS.md) and the related README descriptions
up to date whenever meeting behavior changes. This includes Activity routes or
payload fields, calendar-event selection, identity bindings, Work IQ
paths and query fields, recording/transcript retrieval, persisted state, and
source-link rendering.

Update the object relationships, per-payload pointer tables, synthetic examples,
lookup flow, limitations, and source references affected by the change. State
expected payload fields and object relationships directly, distinguishing fields
the sample consumes from fields present but unused or available through APIs.
Update that expected behavior when newly discovered edge cases require changes.
Never add real meeting content, tenant/user IDs, artifact IDs, credentials, or
live notification URLs to documentation examples.

## Hosted session and lock scope

`azure.yaml` deploys this sample as a Foundry-hosted Microsoft 365 Autopilot
using the Activity protocol. Its hosted Teams delivery uses conversation-scoped
sessions. Foundry gives each session a dedicated VM-isolated sandbox, so unrelated
conversations do not share a Python process or its in-memory locks.

See [Foundry hosted-agent isolation](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#isolation-model)
and [sessions and conversations](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#sessions-conversations-and-the-state-store).

`MeetingHandlers.lifecycle_lock` in `agent/app.py` belongs to one handler instance
inside that process. It is not a deployment-wide lock. Holding it across state
reload, Work IQ calls, model inference, posting, and readiness retries intentionally
serializes lifecycle turns for the same conversation. Reloading state inside the
lock prevents concurrent turns in that process from acting on stale snapshots.

Recurring meeting occurrences in the same chat share conversation state and this
serialization. Different conversations have separate hosted sandboxes. A shared
local server can handle several chats in one process and serialize them, but that
is a different topology from this sample's hosted deployment.

## Review guidance

- Do not infer cross-conversation blocking merely from the handler-instance lock.
  A finding of that kind needs evidence that distinct conversations actually
  share a process in the targeted deployment.
- Preserve same-conversation state serialization. Do not replace it with
  per-conversation lock management solely to address a hypothetical shared replica.
- Continue reporting demonstrated same-conversation concurrency defects,
  deadlocks, incorrect session routing, or other genuine lifecycle failures.
- The lock is process-local and is recreated on restart. It does not provide
  distributed coordination or cross-replica exactly-once delivery.
