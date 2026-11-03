# What this sample demonstrates

A **Copilot SDK support agent** manages synthetic support cases over native
**A2A 1.0**, using **Foundry state storage** to keep records between requests.

```text
Request 1: Open a case       -> create saved record -> case ID
Request 2: Add a finding     -> read + conditional write
Request 3: Add another fact  -> read + conditional write
Request 4: Show case history -> read saved record
Request 5: Summarize         -> read record -> LLM summary -> save summary
```

Each request starts a **fresh Copilot session without conversation history**.
The agent must load cases through its storage tools, not remember previous
messages. The same signed-in caller can use the case ID in another hosted session.
There is one agent and no Toolbox, external ticketing system or live customer data.

## How it works

```text
User --A2A--> SupportExecutor
                 |
                 +-- Copilot SDK -> Foundry model
                        |
                        +-- open_case
                        +-- add_finding
                        +-- get_case
                        +-- list_cases
                        `-- save_resolution_summary
                                |
                                `-- FoundryStateStore (user_isolation=True)
User <-- A2A Task: readable answer + actual storage-operation receipts
```

The LLM interprets the request, selects tools and writes the resolution summary.
Python performs storage operations, record versioning and conditional writes.
It does not evaluate support diagnoses or determine whether the summary is correct.

### Two different kinds of saved state

| State | Purpose | Identifier |
|---|---|---|
| Application case record | Title, description, findings, current summary and event history, explicitly stored by the custom tools. | `case-<32 hex characters>` |
| A2A Task | Status, messages and output artifacts for one request, persisted by the hosted A2A adapter. | A2A Task UUID |

Use the **case ID** to add findings or retrieve current case history.
Use **`GetTask` with the Task ID** to retrieve an earlier request's saved output.
The two IDs are not interchangeable. A read request creates its own A2A Task
but does not create another case or increment the case version.

### State-store behavior

- `FoundryStateStore.get_or_create("support-cases", user_isolation=True)` resolves
  the application store. It is separate from the adapter's Task store.
- The default application item retention is **30 days**. This is a sample
  workspace, not a permanent case archive.
- Hosted item calls carry the **trusted request's Foundry call ID**, captured
  before the SDK dispatches custom tools. This keeps storage calls associated
  with the incoming caller even across SDK callback tasks.
- Reads and updates verify that the store is configured for user isolation.
  The model cannot select or supply a caller identity.
- Findings use read-modify-write with **`if_match` / ETag**. A concurrent change
  causes a conflict instead of silently losing the other update.
- A generated summary includes the case version it was based on.
  Saving a summary for an older version fails; it must be reread and regenerated.
- Saving a summary sets `status` to `summarized`, not a real-world ticket closure.
- Adding a later finding sets the case back to `open` and clears the current
  summary; older summaries remain in event history.
- Duplicate business requests are **not automatically deduplicated**. Do not
  blindly retry an open/add request after an ambiguous network failure.
- Storage persistence does not restart interrupted model/executor work.
  User isolation is configured, but a two-user cloud-isolation check must be
  performed separately before claiming it was verified.

## Files

```text
support-case/
|-- azure.yaml
|-- open-case.json
|-- get-task.json
`-- src/support-case-agent/
    |-- main.py           # Native A2A server and Task artifacts
    |-- client.py         # Fresh Copilot session and request-scoped state store
    |-- tools.py          # Case operations, history, ETags and tool schemas
    |-- pyproject.toml
    `-- uv.lock
```

No sample tests folder, test client or dedicated test workflow is included.

## Prerequisites

- azd **1.37.2**, agent extension **1.0.0-beta.23** and native A2A CLI preview.
- A Foundry project enabled for native A2A, hosted Task storage and application
  state stores. First-time users:
  [create a project](https://learn.microsoft.com/azure/foundry/how-to/create-projects).
- An existing **`gpt-5-nano`** model deployment and the required project access.
- Python **3.13** for the configured hosted runtime; packages require **3.11+**.
- The pinned Copilot SDK and its CLI runtime must be executable in the environment.

Keep the committed dependency manifest and lock. The AgentServer development-feed
sources remain subject to repository dependency policy; no bypass is added.
Use only dummy incidents and synthetic observations. Do not enter credentials,
customer data or payment details.

## Deploy

From a new empty deployment folder:

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"

azd ai agent init --src . `
    -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/feature/a2a-llm-release-planner/samples/python/hosted-agents/bring-your-own/a2a/support-case/azure.yaml" `
    --project-id "<PROJECT-ARM-ID>" `
    --agent-name "support-case-youralias-01"

azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5-nano
azd deploy support
azd ai agent show support --output json
```

Confirm active status and note the deployed version. The commands below assume
your unique agent's first version is **1**; use its actual version if different.
No new model, Cosmos DB, Storage Account or Toolbox needs to be provisioned by
this sample. Ask the project owner to resolve required service access.
Do not run `azd up` or `azd provision` against a shared project.

## Try the complete workflow

Use the same signed-in user for every request. `--new-session` deliberately
uses a separate hosted session while the case record remains accessible.

### 1. Open a case

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Open a synthetic support case titled Search returns HTTP503. Description: Our dummy search service started returning HTTP503 after a configuration change. No real customer impact. Save it and return the case ID."
```

Expected: a generated `case-...` ID, `status: open` and case version **1**.
Save the exact ID returned; do not make up a case ID.

Alternatively use the supplied [open-case.json](open-case.json):

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --input-file open-case.json --output raw
```

Choose **one** opening command; running both creates two cases.

### 2. Add findings in separate requests

Replace `<CASE-ID>` with the generated ID:

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    'For case <CASE-ID>, add this finding: "A synthetic trace shows that the search index alias is missing."'

azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    'For case <CASE-ID>, add this finding: "Restoring the alias in the dummy environment changed the search response from HTTP503 to HTTP200."'
```

Expected: the same case ID, versions **2** then **3**, with both findings
preserved. These are storage writes, not just model-generated statements.

### 3. Retrieve history

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Show the saved support record <CASE-ID>, including its findings and event timeline."
```

Expected: version **3**, two findings and three events (opened + two findings).
The agent loads the record from storage. It has no prior Copilot conversation.

### 4. Generate and save a resolution summary

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Read case <CASE-ID> and generate a resolution summary from its saved findings. Separate observations from proposed follow-up checks. Save the summary to the case."
```

Expected: a `get_case` read followed by a successful summary write.
The case is now version **4**, status `summarized`, with its findings and history
retained. This does not resolve a real incident.

### 5. Retrieve the saved summary in another session

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Retrieve case <CASE-ID>. Show the saved resolution summary and full event history; do not generate a new summary."
```

Expected: version **4** and the persisted summary, with a `read` receipt and no
new write. Also try:

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw "List my saved support cases."
```

### 6. Inspect storage receipts and earlier Tasks

Every successful request returns two named artifacts:

| Artifact | Contents |
|---|---|
| `support-answer` | Human-readable Copilot answer. |
| `state-store-operations` | Actual tool receipts: store name, backend (`foundry` or `local-file`), action, record snapshot and ETag. Failed tool operations are explicitly recorded as errors. |

The second artifact is produced by Python after actual storage calls, not
invented by the model. Check it when verifying that a write really happened.
`TASK_STATE_COMPLETED` alone can also represent an explanation of a failed tool
call: inspect receipts before marking the business operation successful.
An HTTP 200 response may contain a JSON-RPC error.

To retrieve an earlier A2A Task, edit [get-task.json](get-task.json) with that
Task's ID (not the case ID), then run:

```powershell
azd ai agent invoke support-case-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --input-file get-task.json --output raw
```

Expected: its original artifacts, not the current case record. A later finding
does not rewrite an old completed Task.

## More state-store cases to try

| Action | Expected |
|---|---|
| Read a nonexistent case ID | Explicit not-found result, never invented history. |
| Add a finding after saving a summary | Case reopens; current summary clears; old summary remains in history. |
| Two simultaneous updates | ETag conflict rather than silent lost update. Inspect failed tool receipt and reread. |
| Summarize while a finding is added | Stale version/ETag prevents storing a summary based on the old record. |
| Start another hosted session and read by case ID | Saved record loads without conversation memory. |

The walkthrough does not force container restarts or establish different physical
containers merely by using new session IDs.

## Troubleshooting

| Symptom | Check |
|---|---|
| Write fails with "requires a resolved user identity" | Preserve the incoming trusted call ID when constructing the storage tools; do not inject a user ID or disable isolation. |
| A case is not found | Same project, agent, caller, store name and exact case ID; local and hosted stores are separate. |
| Summary save conflicts | Read the latest version and regenerate from the current findings. Do not retry the old overwrite. |
| Model/API request fails or is content-filtered | The error is not a successful write. Inspect receipts and logs; retry only after understanding whether any operation already committed. |
| Model says it saved something | Confirm the matching successful action in `state-store-operations`. |

## Local run

From [src/support-case-agent](src/support-case-agent):

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "<PROJECT-ENDPOINT>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5-nano"
$env:CASE_STORE_NAME = "support-cases-local"
$env:AGENTSERVER_STATE_ROOT = "$PWD\.agent-state"
$env:PORT = "8088"
uv run --frozen --python 3.13 python main.py
```

The Core state store uses a **local file backend** outside hosted Foundry.
Local state is not synchronized to the hosted store and is not proof of cloud
user isolation. Stop and restart with the same state root and store name to
retrieve the saved local case. The A2A adapter's local Task store defaults to
in-memory; application case persistence and local Task persistence are different.

## Cleanup

The tools deliberately do not expose destructive store deletion to the model.
Application items follow the configured retention. Deleting a case record would
not erase historical A2A Task artifacts; this is not a comprehensive erasure demo.
Delete only your own deployed agent through the normal project cleanup process.
Do not delete a shared project or model and do not run `azd down` on one.
