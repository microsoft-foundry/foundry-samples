# What this sample demonstrates

A native A2A agent that saves complete Task snapshots for later retrieval.
Send `remember this result` and receive `Persisted: remember this result`.
No model deployment or API key is required.

## How it works

The executor creates a Task, adds the output artifact and completes it.
Locally, the sample explicitly uses Core's file-backed `FoundryTaskStore`.
When hosted, it uses the host's default agent-scoped Foundry store.

Task snapshots contain status, history and artifacts. Keeping the same local
data directory and store namespace allows reads after restarting the process.
See [main.py](src/persistent-a2a/main.py) for the implementation.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration)
for deployment environments and dependency guidance.

## Prerequisites

1. **Python 3.13** and **uv 0.11.7 or later**.
2. A writable local data directory for local persistence.
3. For deployment, access to a Foundry project with native A2A and managed
   state-store support, including the trusted caller-context handoff.
4. Permission to deploy/invoke agents and use the requested public Task methods.

This preview pins A2A `1.0.0a20261029006` and Core `2.3.1a20261029006`.
The committed project and lock map those packages to the public Azure SDK dev
feed; other dependencies come from PyPI. No feed login or global index
configuration is required.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Use azd **1.37.2** and agent extension **1.0.0-beta.23**, the tested versions.
For a first extension installation, replace `update` with `install`.

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
```

Set the switch in each terminal. Confirm subscription/service enablement with
the project owner; the CLI switch alone does not enable managed persistence.

### Initialize the agent project

Create an empty folder and open a terminal there. Replace `<PROJECT-ARM-ID>`
and choose a unique agent name:

```powershell
azd ai agent init --src . `
  -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/43409818cf6472a15a1d11d01bc7f1f0ec41fa2a/samples/python/hosted-agents/bring-your-own/a2a/task-persistence/azure.yaml" `
  --project-id "<PROJECT-ARM-ID>" --agent-name "persistent-youralias-01"
```

azd adopts the sample's [azure.yaml](azure.yaml) in the current directory.
For a local clone, use this sample's absolute manifest path instead of the
GitHub URL.
If prompted, confirm the intended existing project and unique agent name.
Skip model configuration; this sample does not require a model.

### Provision Azure resources (if needed)

Skip provisioning for this existing-project path.
Do not run `azd provision` or `azd down` against shared resources.

### Run the agent locally

```powershell
uv venv --python 3.13 ".\src\persistent-a2a\.venv"
azd ai agent run --no-client --start-command "python main.py"
```

The server listens on `http://localhost:8088`.
Local snapshots default to `.agentserver` under your home directory;
`AGENTSERVER_STATE_ROOT` optionally selects another location.

Beta.23 cannot invoke A2A with `azd ai agent invoke --local`.
The [sample tests](../README.md#tests) verify local write/restart/read behavior;
use the hosted path below for CLI messages.

### Deploy to Foundry

Stop the local server with Ctrl+C. From the initialized project root:

```powershell
azd deploy persistent-a2a
azd ai agent show --output json
```

Confirm `active` status and copy the deployed version.
No model or Dockerfile is required.

### Invoke the deployed agent

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --new-session "remember this result"
```

Expected answer: `Persisted: remember this result`.
Add `--output raw` to inspect the completed Task and copy its ID.

## Option 2: VS Code (manual Python debugging)

1. Install the VS Code Python extension and open `src/persistent-a2a`.
2. Start once to create the locked environment:

   ```powershell
   uv run --frozen --python 3.13 python main.py
   ```

3. Stop with Ctrl+C and select the generated `.venv` using
   **Python: Select Interpreter**.
4. Open [main.py](src/persistent-a2a/main.py), set breakpoints and choose
   **Python Debugger: Debug Python File**.
5. Keep the same data directory when restarting.

Use an A2A client for local requests; no Agent Inspector integration is assumed.
Use Option 1 to deploy and invoke on Foundry.

## Retrieve and list saved Tasks

From the initialized azd project, save this as `get-task.json`, replacing the
ID with the Task returned by the write:

```json
{
  "jsonrpc": "2.0",
  "id": "read-1",
  "method": "GetTask",
  "params": {"id": "<TASK-ID>"}
}
```

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --input-file get-task.json --output raw
```

Expected: the same Task ID, completed status and artifact. This read must not
send the original message or rerun the executor.

To list that conversation's Tasks, save this as `list-tasks.json`, replacing
`<CONTEXT-ID>` with the context returned by the write:

```json
{
  "jsonrpc": "2.0",
  "id": "list-1",
  "method": "ListTasks",
  "params": {"contextId": "<CONTEXT-ID>", "pageSize": 10}
}
```

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --input-file list-tasks.json --output raw
```

Use the same authenticated caller and agent namespace. Never inject identity
headers or weaken isolation to make a read succeed.

Retrieval alone does not prove a container restart. The
[automated local restart test](../README.md#tests) compares complete Tasks
after stopping the writer and starting a new reader process. Hosted restart
verification additionally needs evidence of distinct runtimes.
Saving a Task does not automatically recover unfinished executor work.

## Troubleshooting

- **Task missing after restart:** check the data directory, namespace and caller.
  Do not resend the original message as a retrieval workaround.
- **Storage authorization error:** check managed storage permissions and trusted
  caller-context handoff. Do not substitute anonymous state.
- **Public Task method rejected:** confirm native gateway availability.
- **Download/TLS error:** check access to PyPI and the public dev feed without
  changing the pins or disabling certificate verification.
- **CLI flags are missing:** check beta.23 and the A2A feature switch.

## Next steps

- [Echo](../echo/README.md)
- [Long-running Tasks](../long-running-tasks/README.md)
