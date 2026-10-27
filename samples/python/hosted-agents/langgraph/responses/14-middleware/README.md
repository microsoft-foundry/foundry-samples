# What this sample demonstrates

A LangChain `create_agent` with built-in and custom middleware, hosted on
Microsoft Foundry over the **Responses protocol**. The email tool is simulated;
no real email is sent.

Ported from [langchain-ai/langchain-azure PR #1179](https://github.com/langchain-ai/langchain-azure/pull/1179),
using the [merged sample at `ed7b1ee`](https://github.com/langchain-ai/langchain-azure/tree/ed7b1ee2d9b7b94ddaa3ae5d73317b6bc504952e/samples/hosting/langgraph-hosted-agents/responses/11_middleware)
as the baseline. Unlike [07-human-in-the-loop](../07-human-in-the-loop/), which
implements its own review node, this sample uses native LangChain middleware.

### Port boundary

| Area | Relationship to the fixed upstream baseline |
| --- | --- |
| `agent.py`, `client.py` | Unchanged upstream implementation, including the native review protocol and simulated tool. |
| `main.py` | Same explicit resource/tracing ownership; only the fallback model name changes from `gpt-4.1-mini` to the manifest's `gpt-5.4-mini`. |
| Foundry integration | Repository-native `azure.yaml`, `src/<service>` layout, code/container packaging, frozen uv runtime/dev dependencies, indexes, and acceptance tests. |
| `07-human-in-the-loop` | Separate repair of the existing graph-review example, not part of the upstream middleware implementation. |

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
host and deployment manifest. Enabling either can export messages, tool
arguments, and results. These switches control telemetry, not checkpoint or
Responses persistence; stored conversations and checkpoints still contain
message/tool content. Use only synthetic email data when trying the sample.

Tracing uses Application Insights when available, or an OTLP HTTP exporter when
`OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set.
Set `OTEL_SDK_DISABLED=true` to disable tracing locally.

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
azd provision
```

Select the new-project path in the prompts. Provisioning creates the manifest's
declared resources and model deployment, so review region, model version, SKU,
and capacity before confirming. `AZURE_AI_MODEL_DEPLOYMENT_NAME` must be the
resulting **deployment name**, not just the model family.

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
use the Toolkit's [Copilot configuration tools](https://code.visualstudio.com/docs/intelligentapps/copilot-tools#generate-and-test-agent-code)
in the sample root and request configuration for the **existing** project:

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

Or run manually from `src/langgraph-middleware`:

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
| `client.py` | Verified | All three verified | JSON and SSE verified | Real-SDK regressions; live-model acceptance is recorded per head in the PR. |
| `azd ai agent invoke` | Verified | Use `client.py` for structured decisions | Not separately accepted | azd 1.37.1 / extension beta.15 wrapped `--input-file` as text, not structured resume fields. |
| Local Agent Inspector | Not visually verified | Not visually verified | Not visually verified | Manual Toolkit acceptance remains required; this is not a claim of unsupported behavior. |
| Foundry portal Playground | Not visually verified | Not visually verified | Not visually verified | Deployment/invocation success does not prove this UI's review behavior. |

For manual Toolkit acceptance, record the exact Git head, Toolkit/Python/debugpy
versions, and generated launch command. In a clean workspace, follow the setup
above, press F5, check Inspector reports **Connected**, hit a breakpoint, and
confirm an email prompt pauses before any `send_email` execution. Run all three
client decisions and confirm only approve/edit emit a tool receipt. Record
Inspector's own controls/streaming separately. The automated DAP attach/readiness
test validates debugger startup without desktop automation; it is **not** an
F5/Inspector UI acceptance result.

## Validation

From `src/langgraph-middleware`, run the credential-free regression suite:

```bash
uv sync --frozen --group dev
uv run --frozen --group dev python -m pytest tests -q
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check .
```

The tests use real LangChain middleware and the real Responses host, replacing
external model/network/export boundaries. They cover the actual review client,
JSON/SSE decisions, multi-action edit preservation, near-limit approval,
cross-process persisted Responses recovery, resource cleanup on exit/failure/
cancellation, tracing ownership, and real-span redaction with an enabled-content
positive control. A headless debugpy attach also starts and probes the real host.

The PR's generic [hosted-runtime checks](../../../RUNTIME_VALIDATION.md) discover
this runtime and the graph-HITL runtime from their manifests and run each one's
declared tests, lint, and format commands with frozen dev dependencies and no
Azure credentials. Policy-framework tests are a separate layer, not a substitute
for running these suites. Dev dependencies and tests remain outside production
packages.

The repository's [cloud behavior contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/langgraph/responses/14-middleware/test-spec.yml)
checks the pending email review and that a specifically approved email executes.
The local tests additionally assert no execution before review. The shared cloud
harness supports automatic approval, not edit
or rejection; use the local tests and review client for those decisions.
Registering the contract does not itself constitute a successful cloud run.

## Troubleshooting

- **Missing project endpoint:** set `FOUNDRY_PROJECT_ENDPOINT` in the source
  directory's `.env`, or initialize the project with `azd` first.
- **Model not found:** set `AZURE_AI_MODEL_DEPLOYMENT_NAME` to your actual
  deployment name, not merely a model family name.
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
do not erase persisted Responses/checkpoints. Test fixtures use their own
temporary state roots and clean those roots automatically.

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

- [Human-in-the-Loop graph sample](../07-human-in-the-loop/)
- [Observability sample](../08-observability/)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
