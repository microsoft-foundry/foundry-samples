# What this sample demonstrates

A minimal native A2A 1.0 hosted agent using the Bring Your Own approach in
Python. Send `hello` and receive a completed Task containing `Echo: hello`.
No model deployment or API key is required.

## How it works

The native `a2a-sdk` provides the Agent Card, executor, Tasks and artifacts.
`azure-ai-agentserver-a2a` hosts the executor on Foundry's A2A routes and
provides readiness, lifecycle, request context and telemetry.

The executor creates a Task, adds the echoed text as an artifact, and completes
the Task. See [main.py](src/echo-a2a/main.py) for the implementation.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration)
for deployment environments and dependency guidance.

## Prerequisites

1. **Python 3.13** and **uv 0.11.7 or later**.
2. For deployment, access to a Foundry project enabled for native A2A.
3. Permission to deploy and invoke agents in that project.

This preview pins A2A `1.0.0a20261029006` and Core `2.3.1a20261029006`.
The committed project and lock fetch those two alpha packages from the public
Azure SDK dev feed and other dependencies from PyPI. No feed login, global
index settings or separate dependency installation is needed.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Use azd **1.37.2** and agent extension **1.0.0-beta.23**, the tested versions.
Update an installed extension below; for a first installation, replace
`update` with `install`.

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
```

Set the feature switch in each terminal used for A2A commands.
The CLI switch does not enable native A2A on your subscription; confirm
service availability with your project owner.

### Initialize the agent project

Create an empty folder and open a terminal there. Replace `<PROJECT-ARM-ID>`
with your existing Foundry project's ARM resource ID and choose a unique
agent name:

```powershell
azd ai agent init --src . `
  -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/43409818cf6472a15a1d11d01bc7f1f0ec41fa2a/samples/python/hosted-agents/bring-your-own/a2a/echo/azure.yaml" `
  --project-id "<PROJECT-ARM-ID>" --agent-name "echo-youralias-01"
```

azd downloads the sample and adopts its [azure.yaml](azure.yaml) in the current
folder. If you already cloned the repository, use the absolute path to this
sample's `azure.yaml` instead of the GitHub URL.
If prompted, confirm the intended existing project and unique agent name.
Skip model configuration; Echo does not require a model.

### Provision Azure resources (if needed)

This walkthrough uses an existing project, so skip provisioning.
Do not run `azd provision` or `azd down` against shared resources.

### Run the agent locally

From the initialized project directory:

```powershell
uv venv --python 3.13 ".\src\echo-a2a\.venv"
azd ai agent run --no-client --start-command "python main.py"
```

The server listens on `http://localhost:8088`. In a second terminal, open
`src\echo-a2a` in that project and run:

```powershell
uv run --frozen --python 3.13 python test_client.py --message "hello"
```

Expected output includes a Task ID and `Echo: hello`.
The sample-local client checks discovery, the artifact and `GetTask`.
Beta.23 does not support A2A invocation with `azd ai agent invoke --local`.

### Deploy to Foundry

Stop the local server with Ctrl+C. From the initialized project root:

```powershell
azd deploy echo-a2a
azd ai agent show --output json
```

Confirm the agent is `active` and copy its `version`. The manifest uses direct
code deployment; no Dockerfile or model deployment is needed.

### Invoke the deployed agent

Replace `<VERSION>` with the deployed version:

```powershell
azd ai agent invoke -p a2a --a2a-version 1.0 --version "<VERSION>" --new-session "hello"
```

Expected answer: `Echo: hello`.
Add `--output raw` to inspect the completed Task and its artifact.

## Option 2: VS Code (manual Python debugging)

1. Install the VS Code Python extension.
2. Open `src/echo-a2a` as your workspace folder.
3. Run the server to create the locked environment automatically:

   ```powershell
   uv run --frozen --python 3.13 python main.py
   ```

4. Stop it with Ctrl+C. Run **Python: Select Interpreter** and select the
   generated `.venv`.
5. Open [main.py](src/echo-a2a/main.py), set a breakpoint, and choose
   **Python Debugger: Debug Python File**.
6. Invoke it from another terminal with the sample-local client shown above.

Use Option 1 to deploy and invoke on Foundry. No Agent Inspector integration
is required for this native A2A sample.

## Troubleshooting

- **Dependency download fails:** check access to PyPI and the public Azure SDK
  dev feed. Resolve TLS/proxy/certificate failures without changing the lock
  or disabling TLS verification.
- **A2A CLI flags are missing:** check extension beta.23 and the feature switch.
- **Agent version is wrong after redeploy:** copy the active version and invoke
  it explicitly with `--new-session`.
- **Local Card discovery fails:** the local Card is at
  `/a2a/.well-known/agent-card.json`, not the public Foundry Card route.
- **Public A2A operation is rejected:** confirm project access and native A2A
  availability. Do not substitute another protocol.

## Next steps

- [Long-running Tasks](../long-running-tasks/README.md)
- [Task persistence](../task-persistence/README.md)
