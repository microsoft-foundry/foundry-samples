# What this sample demonstrates

A native A2A report agent that demonstrates Task submission, polling and
cancellation. Send `quarterly results` and receive
`Report: quarterly results`. No model deployment or API key is required.

## How it works

The executor creates a Task, marks it working, waits two seconds, adds a report
artifact and completes the Task. An immediate-return request lets a client
poll with `GetTask` or cancel active work with `CancelTask`.

The native `a2a-sdk` owns the Task lifecycle.
`azure-ai-agentserver-a2a` provides Foundry hosting and default Task storage.
See [main.py](src/report-a2a/main.py) for the implementation.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration)
for deployment environments and dependency guidance.

## Prerequisites

1. **Python 3.13** and **uv 0.11.7 or later**.
2. For deployment, access to a Foundry project enabled for native A2A.
3. Permission to deploy and invoke agents. The Task examples additionally
   require public `GetTask` and `CancelTask` support.

This preview pins A2A `1.0.0a20261029006` and Core `2.3.1a20261029006`.
The project and committed lock fetch those two packages from the public Azure
SDK dev feed and other dependencies from PyPI. No global feed configuration
or separate dependency installation is needed.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Use azd **1.37.2** and agent extension **1.0.0-beta.23**, the tested versions.
For a first extension installation, replace `update` with `install`.

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
```

Set the switch in each terminal. Confirm service-side A2A enablement with your
project owner; the CLI switch does not enable your subscription.

### Initialize the agent project

Create an empty folder and open a terminal there. Replace `<PROJECT-ARM-ID>`
and choose a unique name:

```powershell
azd ai agent init --src . `
  -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/43409818cf6472a15a1d11d01bc7f1f0ec41fa2a/samples/python/hosted-agents/bring-your-own/a2a/long-running-tasks/azure.yaml" `
  --project-id "<PROJECT-ARM-ID>" --agent-name "report-youralias-01"
```

azd adopts the sample's [azure.yaml](azure.yaml) in the current folder.
If you already cloned the repository, use this sample's absolute manifest
path instead of the GitHub URL.
If prompted, confirm the intended existing project and unique agent name.
Skip model configuration; this sample does not require a model.

### Provision Azure resources (if needed)

Skip provisioning when targeting this existing project.
Do not run `azd provision` or `azd down` against shared resources.

### Run the agent locally

```powershell
uv venv --python 3.13 ".\src\report-a2a\.venv"
azd ai agent run --no-client --start-command "python main.py"
```

The server listens on `http://localhost:8088`.
Beta.23 cannot invoke A2A with `azd ai agent invoke --local`; use the deployed
agent below for CLI invocation. Local lifecycle tests are listed in the
[sample index](../README.md#tests).

### Deploy to Foundry

Stop the local server with Ctrl+C. From the initialized project root:

```powershell
azd deploy report-a2a
azd ai agent show --output json
```

Confirm `active` status and copy the deployed version.
No Dockerfile or model deployment is required.

### Invoke the deployed agent

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --new-session "quarterly results"
```

Expected answer: `Report: quarterly results`.
This plain-message request waits for completion; it does not demonstrate
polling or cancellation.

## Option 2: VS Code (manual Python debugging)

1. Install the VS Code Python extension and open `src/report-a2a`.
2. Start the server once to create the locked environment:

   ```powershell
   uv run --frozen --python 3.13 python main.py
   ```

3. Stop with Ctrl+C and select the generated `.venv` using
   **Python: Select Interpreter**.
4. Open [main.py](src/report-a2a/main.py), set a breakpoint and choose
   **Python Debugger: Debug Python File**.

Use an A2A client for local requests; no Agent Inspector integration is assumed.
Use Option 1 for deployment and hosted CLI invocation.

## Task submission, polling and cancellation

For immediate return, save this as `report-request.json`:

```json
{
  "jsonrpc": "2.0",
  "id": "report-1",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "report-message-1",
      "role": "ROLE_USER",
      "parts": [{"text": "quarterly results"}]
    },
    "configuration": {
      "returnImmediately": true,
      "acceptedOutputModes": ["text/plain"]
    }
  }
}
```

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --input-file report-request.json --output raw
```

Copy `result.task.id`. Save either request below as `task-request.json`,
replacing `<TASK-ID>`:

| Operation | JSON request |
|---|---|
| Read/poll | `{"jsonrpc":"2.0","id":"read-1","method":"GetTask","params":{"id":"<TASK-ID>"}}` |
| Cancel active work | `{"jsonrpc":"2.0","id":"cancel-1","method":"CancelTask","params":{"id":"<TASK-ID>"}}` |

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --input-file task-request.json --output raw
```

Polling should eventually return `TASK_STATE_COMPLETED` with the report.
Successful cancellation returns `TASK_STATE_CANCELED` without a report artifact.
The sample finishes in two seconds, so separate manual CLI calls can miss the
cancellation window. A completed Task is not cancelable. The
[automated sample tests](../README.md#tests) exercise active cancellation
without that manual delay.

Use fresh request/message IDs when repeating requests.
Task data persistence does not resume report execution after process termination.

## Troubleshooting

- **Dependency download fails:** check PyPI/dev-feed access and TLS/proxy
  configuration. Do not change the pins or enable prereleases globally.
- **No immediate response:** send `configuration.returnImmediately: true`.
- **Cancellation is rejected:** check whether the two-second report already
  completed; a client timeout does not cancel work.
- **Public Task method is rejected:** confirm the gateway supports the requested
  native method. Local support does not establish public availability.
- **CLI flags are missing:** check extension beta.23 and the A2A feature switch.

## Next steps

- [Echo](../echo/README.md)
- [Task persistence](../task-persistence/README.md)
