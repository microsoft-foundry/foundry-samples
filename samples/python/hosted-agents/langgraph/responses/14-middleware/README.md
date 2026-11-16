# What this sample demonstrates

A LangChain `create_agent` with built-in and custom middleware, hosted on
Microsoft Foundry over the **Responses protocol**. The email tool is simulated;
no real email is sent.

Ported from [langchain-ai/langchain-azure PR #1179](https://github.com/langchain-ai/langchain-azure/pull/1179),
using the [merged sample at `ed7b1ee`](https://github.com/langchain-ai/langchain-azure/tree/ed7b1ee2d9b7b94ddaa3ae5d73317b6bc504952e/samples/hosting/langgraph-hosted-agents/responses/11_middleware)
as the baseline. Built-in `HumanInTheLoopMiddleware` provides tool approval
for a standard LangChain agent.

### Port boundary

| Area | Relationship to the fixed upstream baseline |
| --- | --- |
| `agent.py`, `client.py` | Unchanged upstream implementation, including the native review protocol and simulated tool. |
| `main.py` | Preserves explicit credential/model/checkpoint lifetimes; adapts the fallback model and delegates telemetry to the stock host instead of also registering the upstream auto-tracer/provider. |
| Foundry integration | Repository-native `azure.yaml`, `src/<service>` layout, code/container packaging, frozen uv runtime/dev dependencies, indexes, and the cloud behavior contract. |

## How it works

- [agent.py](src/langgraph-middleware/agent.py) composes
  [`HumanInTheLoopMiddleware`](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
  with a custom `@before_model` hook. The hook stops the turn at 50 accumulated
  messages before calling the model. It is not a pre-tool limit: a reviewed
  tool can execute on resume before the following model call is stopped.
- [main.py](src/langgraph-middleware/main.py) connects `ChatOpenAI` to the Foundry
  project endpoint using `DefaultAzureCredential`, `use_responses_api=True`, and
  `output_version="responses/v1"`.
- `ResponsesHostServer` handles interrupt serialization and resume translation;
  `FoundryCheckpointSaver` persists graph state locally during development and
  in Foundry State Store when deployed. Preserve the same local state root when
  restarting a paused local run; see [cleanup and local state](#cleanup-and-local-state).
  The explicit host entry point owns the async
  checkpoint and model-client lifetimes; it does not reimplement middleware.
- [client.py](src/langgraph-middleware/client.py) displays the proposed actions,
  then resumes the paused response using `previous_response_id`.

| Decision | Expected result |
| --- | --- |
| Approve | Execute the proposed simulated email. |
| Edit | Replace only the recipient, preserving subject and body. The tool receipt reports the executed arguments. |
| Reject | Feed rejection back to the agent without executing the tool. |

Approve and reject use `mcp_approval_response`. Edit uses the paired
`__hosted_agent_adapter_interrupt__` function-call channel with native
LangChain `decisions` wrapped in an interrupt-keyed `resume` payload. A rejected
tool action is middleware feedback, not a rejected host-level interrupt.

### Tracing and privacy

Both `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` and
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` default to `false` in the
host and deployment manifest. Opting into content capture can export messages,
tool arguments, and results. These switches control telemetry, not checkpoint or
Responses persistence; stored conversations and checkpoints still contain
message/tool content. Use only synthetic email data when trying the sample.

The stock host owns LangChain instrumentation, exporters, and Foundry span
enrichment. Do **not** also call `enable_auto_tracing()` or install a second
LangChain tracer: composing both with the locked SDK duplicates model/tool
spans. This is an intentional adaptation of the upstream entry point, not a
replacement for native middleware. Global telemetry lifetime follows the host
SDK; the sample does not replace or shut down an externally supplied provider.

Set `APPLICATIONINSIGHTS_CONNECTION_STRING` for Azure Monitor or
`OTEL_EXPORTER_OTLP_ENDPOINT` for OTLP HTTP export. With signal-specific OTLP
configuration, set the traces, logs, and metrics endpoints explicitly; unset
signals can use exporter defaults rather than becoming disabled.
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` controls the stock
LangChain instrumentation's content capture. Keep both content flags false for
the default redacted path. Set `OTEL_SDK_DISABLED=true` to disable telemetry.

## Prerequisites

- An Azure subscription with access to hosted agents and a Foundry project with
  a chat model deployment. The manifest provisions `gpt-5.4-mini` by default;
  change its model, version, and SKU if your region requires another model.
- **Python 3.13+**, matching the declared hosted runtime.
- **uv 0.11.7**, matching this repository's dependency-policy validation version.
- Permission to provision the declared resources, or access to an existing
  project and model deployment.

### Configuration and identity boundaries

| Execution identity | Required configuration | Permission scope |
| --- | --- | --- |
| Local host developer | `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and Azure credentials (`az login` for the manual path) | Model inference through the project; `Foundry User` at project scope is a suitable built-in role. |
| Local review client | A running host; optional `--base-url` | No Azure credentials or model deployment variable. Local HTTP is not an authenticated public service. |
| Deployer/provisioner | Selected azd environment, project, model deployment, and unique agent name | `Foundry Project Manager` on an existing project. Creating resources also needs ARM creation/role-assignment permissions; the quickstart uses resource-group `Owner`. Container publishing additionally needs registry push access. |
| Deployed review client | `FOUNDRY_PROJECT_ENDPOINT`, Azure credentials, `--agent-name` | `Foundry Agent Consumer` on the project or agent; no model deployment variable. |
| Runtime agent identity | Platform-provided identity/project/state configuration and the manifest's model deployment name | Foundry supplies normal project model and session-storage access. Grant extra resource permissions only if you add real external tools. |

`azd auth login` signs in the deployment tooling; `DefaultAzureCredential` used
by a manually started Python host/client can use `az login`. The simulated email
tool needs no email-service credentials. See the [permission matrix](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-permissions)
and [deployment identity guidance](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent#required-permissions)
before assigning roles.

## Option 1: Azure Developer CLI (`azd`)

### Set up and initialize

Install [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd),
then install the Foundry extension and authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
mkdir hosted-langchain-middleware
cd hosted-langchain-middleware
```

Choose **one** initialization path below. When testing an unmerged PR, replace
`main` in the manifest URL with the PR branch. Choose an agent name you own:
reusing a name in a shared project creates another version of that existing agent.

**Create a project/model deployment:**

```bash
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/14-middleware/azure.yaml --agent-name my-middleware-agent
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5.4-mini
azd provision
```

Select the new-project path in the prompts. Provisioning creates the manifest's
declared resources and model deployment, so review region, model version, SKU,
and capacity before confirming. `AZURE_AI_MODEL_DEPLOYMENT_NAME` must be the
resulting **deployment name**, not just the model family.
The command above selects the manifest's default deployment; replace it if you
choose a different deployment. Set it explicitly: the tested extension beta.15
provisioned the model from the unified manifest without populating this azd
environment value automatically.

**Reuse an existing project/model deployment:**

```bash
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/14-middleware/azure.yaml --project-id "<Foundry-project-ARM-resource-ID>" --model-deployment "<existing-deployment-name>" --agent-name my-middleware-agent
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<existing-deployment-name>"
```

The project ID is the full ARM ID, ending in
`/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>`;
it is not the HTTPS project endpoint. Skip `azd provision` when all selected
dependencies already exist. Provision only deliberately added missing resources.
The selected azd value feeds
`services.langgraph-middleware.env.AZURE_AI_MODEL_DEPLOYMENT_NAME` in
`azure.yaml` for local run/deployment. For the manual path, copy the same
deployment name and HTTPS project endpoint into the source directory's `.env`.

### Run the agent locally

```bash
azd ai agent run --no-client
```

The host listens on `http://localhost:8088`.

### Invoke the local agent

In another terminal, from the initialized project directory:

```bash
azd ai agent invoke --local "Hello!"
```

Use the [review client](#review-an-email) for the full approve/edit/reject flow.
A plain invocation of an email prompt pauses; it does not send an email.

### Deploy to Foundry

```bash
azd deploy
```

The manifest defaults to **direct code deployment** (`codeConfiguration`). This
path does not require Docker on your machine.

The sample also includes a [Dockerfile](src/langgraph-middleware/Dockerfile) and
[.dockerignore](src/langgraph-middleware/.dockerignore), matching neighboring
samples. To use container deployment, install and start Docker, initialize a
separate workspace with the same manifest URL and `--deploy-mode container`,
then follow the same provision/deploy steps. The image uses Python 3.13 and
uv 0.11.7 and installs only the frozen production dependencies.

Repository cloud CI validates both container and direct-code deployment. The
Dockerfile is excluded from direct-code uploads by `.agentignore`; local
environments, secrets, tests, and generated state are excluded from the image.

### Invoke the deployed agent

```bash
azd ai agent invoke "Hello!"
```

## Option 2: VS Code (Foundry Toolkit)

### Set up the environment

Install [VS Code](https://code.visualstudio.com/), the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio),
the Python extension, and [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
Sign in with `az login`, clone this repository, and open this sample folder.

From the VS Code terminal:

```bash
cd src/langgraph-middleware
uv sync --frozen --group dev
```

Copy [.env.example](src/langgraph-middleware/.env.example) to `.env` in that source
directory. Set `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME` for your existing project. Do not commit `.env`.
Select the source directory's `.venv` interpreter in VS Code.

### Run and debug

Cloning this repository does **not** create a debug workspace. Before using F5,
create the local files in [Deterministic F5 setup](#deterministic-f5-setup-windows),
or use the Toolkit's [Copilot configuration tools](https://code.visualstudio.com/docs/intelligentapps/copilot-tools#generate-and-test-agent-code)
in the sample root to configure the **existing** project:

This configuration-generation route requires **GitHub Copilot Chat access in
VS Code**, enabled Foundry Toolkit tools, and the sample folder opened as the
workspace; see the [Copilot tools prerequisites](https://code.visualstudio.com/docs/intelligentapps/copilot-tools#prerequisites).
Without that access, use the deterministic F5 configuration, manual run, or
`azd`; running and debugging this sample do not require Copilot. Configuration
generation alone is not evidence that F5 or Inspector works.

```text
Configure this existing LangChain hosted agent for local debugging with
Foundry Toolkit and Agent Inspector. Preserve agent.py, main.py, and client.py.
Use src/langgraph-middleware/main.py, its .venv interpreter and source .env,
debugpy port 5679, and HTTP port 8088. Generate the workspace .vscode launch
and task configuration only; do not provision resources or deploy.
```

Review the generated interpreter, working directory, environment file, and
entry point before running **Debug Local Agent HTTP Server** with **F5**.
`debugpy` is locked in the dev group, not installed into the production image.
Keep generated `.vscode` files local; do not commit them.

#### Deterministic F5 setup (Windows)

This alternative does not use Copilot or provision resources. Open the sample
root in VS Code, complete the source `.env` and frozen dev-dependency setup
above, and create these two **local, uncommitted** files. Close any existing
sample host first so ports 5679 and 8088 are available.

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Local Agent HTTP Server",
      "type": "debugpy",
      "request": "attach",
      "connect": { "host": "127.0.0.1", "port": 5679 },
      "justMyCode": true,
      "preLaunchTask": "Start Middleware Debug Server"
    }
  ]
}
```

`.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start Middleware Debug Server",
      "type": "process",
      "command": "${workspaceFolder}/src/langgraph-middleware/.venv/Scripts/python.exe",
      "args": [
        "-m", "debugpy", "--listen", "127.0.0.1:5679",
        "--wait-for-client", "--log-to-stderr",
        "${workspaceFolder}/src/langgraph-middleware/main.py"
      ],
      "options": {
        "cwd": "${workspaceFolder}/src/langgraph-middleware",
        "env": {
          "PORT": "8088",
          "AGENTSERVER_STATE_ROOT": "${workspaceFolder}/.ui-acceptance-state",
          "PYTHONNOUSERSITE": "1"
        }
      },
      "isBackground": true,
      "problemMatcher": {
        "owner": "middleware-debug",
        "pattern": { "regexp": "^(THIS_PATTERN_NEVER_MATCHES)$", "message": 1 },
        "background": {
          "activeOnStart": true,
          "beginsPattern": ".*",
          "endsPattern": "wait_for_client\\(\\)"
        }
      },
      "presentation": { "reveal": "never", "panel": "dedicated" }
    }
  ]
}
```

On macOS/Linux, change the task's Python executable to
`${workspaceFolder}/src/langgraph-middleware/.venv/bin/python`; the Windows
configuration above is the one covered by desktop acceptance. The task runs
from the source directory, where `main.py` loads `.env`, and preserves a
sample-owned state root across restarts. It does not depend on VS Code's global
Python interpreter selection.

Select **Debug Local Agent HTTP Server** and press **F5**. Set a breakpoint on
the message-count check in `agent.py`, open Inspector as described below, and
send a greeting to hit it. Inspect the state, step, and continue the request.
With this attach configuration, **Shift+F5 disconnects the debugger but leaves
the background server task running**. Use **Terminal > Terminate Task > Start
Middleware Debug Server** to stop that task before starting another host or
cleaning its state.

#### Run without a debugger

From `src/langgraph-middleware`:

```bash
uv run --frozen main.py
```

Then open **Agent Inspector** under **Foundry Toolkit > Developer Tools > Build**
and connect to `http://localhost:8088`. Opening Inspector alone neither starts
the server nor attaches a debugger. Follow the [Inspector connection guide](https://code.visualstudio.com/docs/intelligentapps/agent-inspector#connect-and-debug).
Use `client.py` for the verified approve/edit/reject path.

### Deploy to Foundry

Run **Foundry Toolkit: Deploy Hosted Agent**, select your Foundry project,
choose **Code**, confirm `main.py` as the entry point, and deploy. Invoke the
agent in the playground and inspect its **Logs** tab.

## Review an email

Run the following commands from `src/langgraph-middleware` in a second terminal
while the local host is running:

```bash
uv run --frozen client.py
uv run --frozen client.py --decision approve
uv run --frozen client.py --decision edit --recipient bob@example.com
uv run --frozen client.py --decision reject
uv run --frozen client.py --stream --decision approve
```

The default prompt proposes an email to `alice@example.com`. The first command
asks for a decision interactively; the others apply the supplied decision.
Each command begins a new review. Inspect the final response for the executed
recipient, subject, and body. Rejection must not execute `send_email`.
The decision applies to **all** proposed actions in that review. This small CLI
handles one review round; it has no resume-existing-response-ID option. Keep the
pending response ID and host state if continuing with your own Responses client.

For a deployed agent, set `FOUNDRY_PROJECT_ENDPOINT`, authenticate with Azure CLI,
and add the registered name shown by your deployment (replace the example name).
The review client does not need `AZURE_AI_MODEL_DEPLOYMENT_NAME`:

```bash
uv run --frozen client.py --agent-name my-middleware-agent --decision approve
uv run --frozen client.py --agent-name my-middleware-agent --decision edit --recipient bob@example.com
uv run --frozen client.py --agent-name my-middleware-agent --stream --decision reject
```

### Frontend coverage and acceptance boundary

| Frontend | Pause | Approve / edit / reject | Streaming | Evidence boundary |
| --- | --- | --- | --- | --- |
| `client.py` | Verified | All three verified | JSON and SSE verified | Local and cloud live-model acceptance is recorded per head in the PR. |
| `azd ai agent invoke` | Verified | Use `client.py` for structured decisions | Not separately accepted | azd 1.37.1 / extension beta.15 wrapped `--input-file` as text, not structured resume fields. |
| Local Agent Inspector | Verified | Native Approve/Deny verified; edit uses `client.py` | SSE verified | Desktop acceptance with Toolkit 1.6.17 includes F5 breakpoint/step/continue and exported response events. Expanded approval controls in this version did not expose Edit. |
| Foundry portal Playground | Not visually verified | Not visually verified | Not visually verified | Deployment/invocation success does not prove this UI's review behavior. |

Head-specific acceptance results are recorded in the PR; the verified Windows
run used Python 3.13.15 and debugpy 1.8.21. Copilot auto-generation and portal
deployment/playground UI are separate paths and are not claimed verified by
that run. For subsequent Toolkit acceptance, record the exact Git head, Toolkit/Python/debugpy
versions, and generated launch command. In a clean workspace, follow the setup
above, press F5, check Inspector reports **Connected**, hit a breakpoint, and
confirm an email prompt pauses before any `send_email` execution. Run all three
client decisions and confirm only approve/edit emit a tool receipt. Record
Inspector's own controls/streaming separately. Headless startup checks do not
replace F5/Inspector UI acceptance.

## Trigger the custom hook

With the local host running, start Python from `src/langgraph-middleware` using
`uv run --frozen python` and send 50 messages:

```python
from openai import OpenAI

with OpenAI(base_url="http://127.0.0.1:8088/", api_key="local") as client:
    response = client.responses.create(
        input=[{"role": "user", "content": "Check the message limit."}] * 50,
    )
    print(response.model_dump_json(indent=2))
```

Expect `Conversation limit reached.` without a model or tool call. This starts
a new request with 50 input messages; it does not send an email or require a
review decision.

## Validation

Follow [the review flow](#review-an-email) against the local host, then repeat
against the deployed agent. Exercise approve, edit, and reject with JSON and SSE.
Confirm the request pauses before `send_email` executes and only approve/edit
produce a tool receipt. Keep local, cloud, and Toolkit acceptance evidence
separate and record the exact Git head and tool versions in the PR.

The repository's [cloud behavior contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/langgraph/responses/14-middleware/test-spec.yml)
checks the pending email review and that a specifically approved email executes.
The shared cloud harness supports automatic approval, not edit or rejection;
use the review client for those decisions. Registering the contract does not
itself constitute a successful cloud run.

## Troubleshooting

- **Missing project endpoint:** set `FOUNDRY_PROJECT_ENDPOINT` in the source
  directory's `.env`, or initialize the project with `azd` first.
- **Model not found:** set `AZURE_AI_MODEL_DEPLOYMENT_NAME` to your actual
  deployment name, not merely a model family name.
- **Package-download TLS failure:** verify access to `files.pythonhosted.org`,
  not just the PyPI index. `uv` does not read `pip.ini`, and frozen installs use
  artifact URLs recorded in `uv.lock`; changing only an index setting may not
  redirect those downloads. Use your organization's approved package/network
  configuration, preserving locked versions and artifact hashes. Do not disable
  TLS verification or change the shared lockfile to embed a private proxy URL.
- **Review not returned:** ask explicitly to send an email with recipient,
  subject, and body. Greetings do not trigger human review.
- **Conversation limit reached:** begin a new conversation. The limit counts
  accumulated graph messages, including tool calls and results.
- **Interrupted local run cannot resume:** retain the same state root and pending
  response ID. Resuming is a Responses `previous_response_id` request, not another
  invocation of the original email prompt. The supplied CLI starts a new review.

## Cleanup and local state

Stop the host/debugger before cleaning local state. With the locked SDK, the
default is `~/.agentserver` (`%USERPROFILE%\.agentserver` on Windows), **not the
working directory**. It may contain other samples' data. For an isolated manual
run, set `AGENTSERVER_STATE_ROOT` in the source `.env` to an absolute directory
owned only by this sample. Keep that value unchanged across process restarts;
do not override the platform's state configuration in `azure.yaml`.

Only delete that verified, sample-owned directory after abandoning its pending
reviews. Do not recursively remove shared `~/.agentserver`. Content-capture flags
do not erase persisted Responses/checkpoints.

For Azure resources, follow the [ownership-aware cleanup guidance](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-deploy-own-code#clean-up-resources):

- **New project created by this azd environment:** `azd down` deletes its entire
  resource group, including other resources added there. Verify ownership first.
- **Reused project:** `azd down` leaves the project **and hosted agent** in place.
  Check `azd ai agent show --output json` in the correct initialized environment.
  Delete only the agent/version created for this exercise. Never delete a shared
  project, model deployment, or another owner's agent.

For extension versions supporting version-scoped deletion (verified with
`azure.ai.agents` beta.15), replace both placeholders after inspecting the output:

```bash
azd ai agent delete "<owned-agent-name>" --version "<owned-version>"
```

Omitting `--version` deletes **all versions** of that agent. Use that only for a
uniquely named agent you own. Check `azd ai agent delete --help` for your installed
extension; do not add `--force` just to bypass active-session protection.

## Next steps

- [Observability sample](../08-observability/)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
