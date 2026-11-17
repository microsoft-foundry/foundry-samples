# What this sample demonstrates

A minimal **native A2A 1.0 Echo agent**. Send `hello`; receive a completed Task
with artifact text **`Echo: hello`**.

No LLM, Copilot SDK, model deployment, Toolbox or application state-store code is
needed. For multi-agent collaboration, see the
[travel planner with web search](../travel-planner-web-search/).

## How it works

[main.py](src/echo-a2a/main.py) contains:

- `EchoExecutor.execute`: create a Task, add the echoed text as an artifact and
  complete the Task.
- `EchoExecutor.cancel`: report that this immediate Echo operation is not cancelable.
- Startup: create an Agent Card and start `A2AAgentServerHost`.

The native SDK and hosting adapter handle the A2A protocol and Task storage.
Locally Tasks are in memory by default. Hosted Tasks use the adapter's Foundry
Task store, which calls Core state storage internally. There is no custom
application-storage wrapper in this sample.

```text
User --A2A SendMessage--> EchoExecutor
User <-- completed Task + "Echo: hello"

User --A2A GetTask--> hosted Task store --> Core/Foundry state storage
User <-- saved Task and artifact
```

## Prerequisites

- Python **3.13**, uv **0.11.7 or later** for local execution.
- azd **1.37.2**, agent extension **1.0.0-beta.23** for hosted deployment.
- A Foundry project enabled for native A2A and hosted Task storage, with
  permission to deploy/invoke agents. First-time users:
  [create a project](https://learn.microsoft.com/azure/foundry/how-to/create-projects).

Keep the provided dependency manifest and lock. AgentServer A2A `1.0.0b1` and
Core `2.3.1b1` are pinned public PyPI beta releases.

## Deploy and invoke

For GitHub templates, install GitHub CLI and run `gh auth login` followed by
`gh auth status` first. The tested extension can start GitHub login for public
templates despite `--no-prompt`. For unattended execution, download/clone the
sample and use its local manifest instead.

From a new empty deployment folder:

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"

azd ai agent init --src . `
    -t "https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/a2a/echo/azure.yaml" `
    --project-id "<PROJECT-ARM-ID>" --agent-name "a2a-echo-youralias-01"

azd deploy echo
azd ai agent show echo --output json
```

Confirm active status. Use the actual deployed version below:

```powershell
azd ai agent invoke a2a-echo-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw "hello"
```

Expected: `TASK_STATE_COMPLETED` and artifact text exactly `Echo: hello`.
The generated Task ID is in `result.task.id`.

For JSON file input, use [echo-request.json](echo-request.json):

```powershell
azd ai agent invoke a2a-echo-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --input-file echo-request.json --output raw
```

### Retrieve the saved Task

Replace `<TASK-ID>` in [get-task.json](get-task.json) with the returned Task ID:

```powershell
azd ai agent invoke a2a-echo-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --input-file get-task.json --output raw
```

Expected: the same completed Task and artifact, without calling the executor
again. Use the same signed-in caller. This does not claim that interrupted
execution resumes or that cross-user isolation has been independently verified.

Inspect the JSON-RPC body, not only HTTP 200: an `error` is not a successful echo.
`--version 1` is the deployed agent version; `--a2a-version 1.0` is the protocol.

### Hosted beta verification

A fresh direct-code deployment with A2A `1.0.0b1` and Core `2.3.1b1` passed
native `SendMessage`: a completed Task containing exactly `Echo: hello`.
`GetTask` with the same caller/session returned the identical stored Task,
including artifacts, history and status. The response's `X-Platform-Server`
header confirmed both beta SDK versions. This does not establish restart
recovery or cross-user isolation.

For JSON-RPC `-32603` or a downstream service 400, inspect the deployed version,
the raw response's SDK header and session console logs; deployment success
alone does not prove invocation works. Older copies of this sample used alpha
SDKs: update both `pyproject.toml` and `uv.lock`, redeploy, and invoke the new
version in a fresh session. Echo requires neither a model nor a Toolbox.

## Optional local run

From [src/echo-a2a](src/echo-a2a), terminal 1:

```powershell
$env:PORT = "8088"
uv run --frozen --python 3.13 python main.py
```

No Azure login or model is required for this local run.
In terminal 2, from the sample root:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8088/a2a" `
    -Headers @{"A2A-Version" = "1.0"} -ContentType "application/json" `
    -Body (Get-Content .\echo-request.json -Raw) | ConvertTo-Json -Depth 20
```

The local Agent Card is at
`http://localhost:8088/a2a/.well-known/agent-card.json`.
Stop the server with Ctrl+C. Restarting the default local server clears its
in-memory Tasks.

## Cleanup

Delete only your uniquely named deployed agent:

```powershell
azd ai agent delete echo --force
```

Run from the initialized project and verify that service `echo` points to your
agent. `--force` terminates active sessions and deletes all agent versions.

Do not delete a shared project/model or run `azd down` against one.
There are no sample test files or test client.
