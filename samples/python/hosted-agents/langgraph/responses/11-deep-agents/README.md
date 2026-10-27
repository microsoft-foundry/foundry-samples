# What this sample demonstrates

Use the **LangChain Azure SDK with LangChain, LangGraph, and Deep Agents** to
research a topic, save a cited report, revise a named copy, and download both
versions from private Azure Blob Storage. Run the same native graph locally or
host it on Microsoft Foundry over the **Responses protocol**.

The scenario brings together SDK model and tool integration, checkpointed Deep
Agents state, a custom LangChain tool, and explicit resource lifetimes. Foundry
project/model configuration, Toolbox deployment, Storage authorization, and cloud
acceptance are included so that the SDK example can be run end to end.

It reuses the selected [LangChain Azure Deep Research example](https://github.com/langchain-ai/langchain-azure/tree/c480d810ca96e77860db64ba3403c3bf13d5dfcf/samples/hosting/langgraph-hosted-agents/responses/12_deep_agents),
adapted to this repository's `src/` layout, uv dependencies, inline Toolbox, and
direct-code deployment. The integration points below explain how to adapt the
framework workflow independently of its deployment.

## How it works

1. `create_deep_agent` plans work and delegates focused searches to
   `research-agent`. Foundry Toolbox supplies `web_search`; a local `think_tool`
   records concise factual progress, not private reasoning.
2. The coordinator saves `/report-v1.md`. Deep Agents' default `StateBackend`
   stores virtual files in conversation state; `FoundryCheckpointSaver` persists
   that state locally or in Foundry State Store when hosted.
3. A follow-up reads the original, writes `/report-v2.md`, edits that copy, and
   reads it back. The original findings and citations remain available.
4. `publish_report(report_name)` reads the selected saved file, uploads a separate
   private Blob snapshot, and returns its SHA256 and a one-hour, read-only HTTPS
   user-delegation SAS. It never accepts a model-supplied upload body or destination.

`main.py` owns the Azure credential, default model clients, and checkpoint saver
until the stock `ResponsesHostServer` shuts down. `agent.py` remains independent
of hosting. Working files are **not** files on the hosted session filesystem;
Blob Storage is an export destination, not a replacement backend.

### SDK and framework integration points

| Integration | Where to read / what it demonstrates |
| --- | --- |
| Azure model as a LangChain chat model | [`main.py`](src/langgraph-deep-agents/main.py) uses `AzureAIOpenAIApiChatModel` with `output_version="responses/v1"` for the native graph's model and tool-call messages. |
| Deep Agents composition on LangGraph | [`agent.py`](src/langgraph-deep-agents/agent.py) uses `create_deep_agent`, a research `SubAgent`, and `TodoListMiddleware`, retaining the default `StateBackend`. The graph does not depend on its HTTP host. |
| Foundry Toolbox as LangChain tools | [`research_agent/tools.py`](src/langgraph-deep-agents/research_agent/tools.py) loads `AzureAIProjectToolbox` and selects only `web_search`, alongside a local progress tool. |
| Checkpointed framework state | [`main.py`](src/langgraph-deep-agents/main.py) supplies `FoundryCheckpointSaver`; reports and todos belong to conversation state rather than the container filesystem. |
| State-aware custom tool | [`report_export.py`](src/langgraph-deep-agents/report_export.py) uses LangChain `ToolRuntime` to publish a selected saved file, not model-supplied upload content. Expected Storage failures become handled tool errors. |
| SDK hosting and lifecycle | [`main.py`](src/langgraph-deep-agents/main.py) keeps credentials, model clients, and the checkpoint saver alive around `ResponsesHostServer`. [`client.py`](src/langgraph-deep-agents/client.py) demonstrates continuation and hosted-session cleanup. |

The sections below add the platform resources, identities, configuration, and
deployment needed by these integrations. Use the same `build_agent` function when
adapting the research workflow; a different host does not require rewriting it.

### Configuration

| Variable | Purpose |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint; injected by Foundry/azd, set manually for a direct local run. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment selected during initialization. |
| `TOOLBOX_NAME` | `deep-agents-tools`, declared in `azure.yaml`. |
| `AZURE_STORAGE_ACCOUNT_NAME` | azd/CI input: existing report Storage account name. |
| `AZURE_STORAGE_CONTAINER_NAME` | azd/CI input: existing private report container. |
| `AZURE_STORAGE_SUBSCRIPTION_ID` | azd/CI input: subscription containing report Storage; defaults to `AZURE_SUBSCRIPTION_ID` when omitted. |
| `REPORT_STORAGE_ACCOUNT_URL` | HTTPS Blob endpoint for your dedicated report account. |
| `REPORT_STORAGE_CONTAINER` | Existing private container, for example `reports`. |
| `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` | Defaults to `false`. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Defaults to `false`. |

`azure.yaml` maps the standard `AZURE_STORAGE_*` inputs to the upstream
`REPORT_STORAGE_*` runtime variables. For standalone Python, fill the latter
values in `.env`; do not rely on azd to export its environment into another shell.

## Prerequisites

1. **Python 3.13+** and [uv](https://docs.astral.sh/uv/getting-started/installation/)
   **0.11.7+** on `PATH`.
2. A Foundry project with a tool-capable model deployment and a Toolbox exposing
   `web_search`. Option 1 provisions these from `azure.yaml` if needed.
3. A dedicated Azure Storage account and private report container. They are
   **not** created by this manifest; setup commands are included below. Storage
   can use another subscription in the same tenant; configure its subscription
   explicitly and ensure the deployer has the required access there.
4. An authenticated Azure identity, for example through `az login`, plus the
   following permissions. Have an RBAC administrator apply missing grants;
   resource Contributor alone cannot assign roles.

| Identity / operation | Required access |
| --- | --- |
| Developer: project and Toolbox access | `Azure AI User` on the Foundry project and Reader on its parent account. |
| Provisioner / deployer | Contributor on the intended resource group, `Azure AI Project Manager` on an existing project, and permission to assign the two Storage roles below. |
| Project managed identity: managed tools | `Azure AI User` on the parent Foundry account when not already provisioned. |
| Local developer: publish reports | `Storage Blob Data Contributor` on the dedicated report **account**. |
| Deployed agent instance identity: publish reports | Container-scoped `Storage Blob Data Contributor` plus account-scoped `Storage Blob Delegator`; the postdeploy hook configures these **separately** from developer access. |

The account-scoped Blob role allows both uploading and requesting the user
delegation key. A narrower alternative is container-scoped `Storage Blob Data
Contributor` plus account-scoped `Storage Blob Delegator`. The project managed
identity and agent `instance_identity.principal_id` are different principals;
the developer's Blob permission does not transfer to the hosted agent.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and
[Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd),
then install the Foundry extension and authenticate:

```bash
azd ext install microsoft.foundry
az login
azd auth login
```

### Initialize the agent project

No cloning required:

```bash
mkdir hosted-langgraph-deep-agent && cd hosted-langgraph-deep-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/11-deep-agents/azure.yaml
```

Follow the prompts to select a Foundry project and model deployment, or create
new ones. The following commands run from this initialized project directory.

### Create private report Storage

Configure the external Storage values before provisioning so that every
`azure.yaml` environment reference is defined.

Use a dedicated account/resource group. Replace the placeholders and choose the
intended subscription explicitly. The identity creating the resources needs
Contributor; the identity granting roles needs RBAC administration rights.

```bash
export SUBSCRIPTION_ID="<subscription-id>"
export LOCATION="<azure-region>"
export REPORT_RESOURCE_GROUP="<dedicated-report-resource-group>"
export REPORT_STORAGE_ACCOUNT="<globally-unique-storage-account>"
export REPORT_STORAGE_CONTAINER="reports"
export DEVELOPER_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)"

az group create --subscription "$SUBSCRIPTION_ID" --name "$REPORT_RESOURCE_GROUP" --location "$LOCATION"
az storage account create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage container-rm create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --storage-account "$REPORT_STORAGE_ACCOUNT" --name "$REPORT_STORAGE_CONTAINER" --public-access off
export REPORT_STORAGE_ACCOUNT_URL="$(az storage account show --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --query primaryEndpoints.blob -o tsv)"
export REPORT_STORAGE_ID="$(az storage account show --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --query id -o tsv)"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$DEVELOPER_OBJECT_ID" --assignee-principal-type User --role "Storage Blob Data Contributor" --scope "$REPORT_STORAGE_ID"

azd env set AZURE_STORAGE_ACCOUNT_NAME "$REPORT_STORAGE_ACCOUNT"
azd env set AZURE_STORAGE_CONTAINER_NAME "$REPORT_STORAGE_CONTAINER"
azd env set AZURE_STORAGE_SUBSCRIPTION_ID "$SUBSCRIPTION_ID"
```

For automation, substitute the actual developer service-principal object ID and
`ServicePrincipal` type. With an existing account, reuse its URL, container, and
resource ID instead of running the create commands, and set
`AZURE_STORAGE_SUBSCRIPTION_ID` to that account's subscription. Storage lookup and
role operations use this value, not the Azure CLI's currently selected subscription.
Retirement cleanup uses the subscription in the recorded Storage account scope.
Allow time for RBAC propagation.

### Provision Azure resources (if needed)

```bash
azd provision
```

The manifest declares the project, model, and connection-free web-search Toolbox.
For an existing project, ensure the project and developer permissions listed above
are in place before provisioning. No external search API key is required.

### Deploy the remote dependencies before local execution

```bash
azd deploy --all
```

This deploys the Toolbox before the agent. The postdeploy hook grants the agent
container data access and account delegation rights, recording only assignments
it creates in `.azure/report-storage-role-assignments.json`. Missing configuration
or role-assignment permission fails deployment rather than silently skipping
authorization. An RBAC administrator can run
`python hooks/configure-report-storage.py` in the initialized project to repair
the grants, then retry deployment.

`azd provision` does not deploy Toolbox services, and `azd ai agent run` does not
create remote tools. Complete this step before either local running or Toolkit F5.

### Run the agent locally

```bash
azd ai agent run --no-client
```

The host listens on `http://localhost:8088`. Local execution still uses the cloud
model, Toolbox, and Blob account; it is not an offline mode.

### Invoke the local agent

In another terminal, from the initialized project directory:

```bash
azd ai agent invoke --local "Research how LangGraph checkpoints support multi-turn agents. Cite primary sources and save report-v1.md."
```

For the complete four-turn research/read/revise/download demo, run the checked-in
client with the same project and Storage environment. It loads the runtime's
`.env`; copy `.env.example` there and fill it in when those values are not already
exported:

```bash
cd src/langgraph-deep-agents
uv sync --frozen
cp .env.example .env
uv run --frozen python client.py
```

### Deploy to Foundry

```bash
azd deploy --all
```

After edits, deploy all services again so the Toolbox and agent configuration stay
aligned. The hook resolves the actual deployed agent, including CI-renamed service
keys, and reuses existing/inherited grants. It never grants access to the project
identity in place of the agent instance or falls back to Storage account keys.

See [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
for the complete deployment workflow. The default is direct code deployment;
Docker is not required. The existing Dockerfile is an optional container path.

### Invoke the deployed agent

From the initialized project directory:

```bash
azd ai agent invoke "Research recent advances in small language models and save report-v1.md."
```

For the complete demo, export `FOUNDRY_PROJECT_ENDPOINT` from
`azd env get-value FOUNDRY_PROJECT_ENDPOINT`, keep the report account/container
values available, and run from `src/langgraph-deep-agents`:

```bash
uv run --frozen python client.py --agent-name langgraph-deep-agents
```

The client binds continuations to the latest response ID and deployed session ID,
verifies the downloaded bytes against each publication digest, and stops only the
returned test sessions on exit. On a handled publication error it exits without
claiming a download; the saved report remains available for a later turn.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

Install the [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
and sign in to Azure. Use a project with a deployed model, the `web_search`
Toolbox, and the private Storage resources and identity grants listed in
Prerequisites. Complete Option 1 through `azd deploy --all` first if remote
dependencies have not already been deployed and authorized.

### Set up the Python environment

Open this sample folder in VS Code. In its terminal:

```bash
cd src/langgraph-deep-agents
uv sync --frozen
cp .env.example .env
```

Fill in `.env`, including the project endpoint, model deployment, Toolbox name,
report account URL, and container. Select `src/langgraph-deep-agents/.venv` as the
Python interpreter. Do not commit `.env` or generated Toolkit configuration.

### Run and debug the agent

Press **F5** using the Toolkit-generated launch/tasks configuration; Agent
Inspector opens automatically. Alternatively, from the runtime directory:

```bash
uv run --frozen python main.py
```

Open Agent Inspector and connect to `http://localhost:8088`. Use the same research
prompt as Option 1. Run `uv run --frozen python client.py` in another terminal for
the complete named-report demo.

### Deploy to Foundry

Use **Deploy Hosted Agent** in Foundry Toolkit for agent-only changes. When the
Toolbox, hooks or Storage settings change, run `azd deploy --all` from the
initialized project so those dependencies and instance grants are updated too.
Test in Agent Inspector or run the deployed demo client.

## Reports, downloads, and privacy

The client creates `/report-v1.md`, reads it back, revises a copy at
`/report-v2.md`, and downloads both snapshots to `~/Downloads/deep-research`
(override with `--output-dir`). `publish_report` accepts a simple filename without
a leading slash: 1-64 ASCII letters, digits, hyphens, or underscores before `.md`,
starting with a letter or digit. Paths and other extensions are rejected.

Each publication creates `<random-prefix>/<report_name>` with a matching attachment
filename and `overwrite=False`. Editing the working file does not change an earlier
download. A SAS is an HTTPS bearer secret, read-only for that one Blob, valid for
one hour. Expiry **does not delete** the Blob; delete snapshots or configure a
retention policy separately. No account keys or public container are used.

Both telemetry content-capture flags default to `false` before host construction.
Opting in may export prompts, search queries, report text, tool results, and SAS
URLs. Keep response histories, client output, and acceptance transcripts private.
Search queries still leave the application, and checkpoints still retain content.
Research budgets are prompt guidance, not enforced runtime limits. This sample
shows checkpointed conversation state, not arbitrary in-flight crash recovery.

## Adapt the SDK example

- Change the research workflow or subagent responsibilities in
  [`research_agent/prompts.py`](src/langgraph-deep-agents/research_agent/prompts.py)
  and [`agent.py`](src/langgraph-deep-agents/agent.py), without changing the host.
- Add SDK Toolbox integrations through
  [`research_agent/tools.py`](src/langgraph-deep-agents/research_agent/tools.py),
  keeping the exposed tools explicit rather than loading unrelated Toolbox tools.
- Add state-aware LangChain tools alongside
  [`report_export.py`](src/langgraph-deep-agents/report_export.py). Keep saved
  framework state separate from exported artifacts and do not accept arbitrary
  model-selected Storage destinations.
- For human approval or durable background execution, follow the separate
  [HITL](../07-human-in-the-loop/) and [Resilient Responses](../09-resilient/)
  SDK integration examples. This research scenario does not implement those
  additional execution policies.

## Validation and cleanup

From `src/langgraph-deep-agents`:

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -v
```

The offline tests use the published SDK, native graph, and stock Responses host;
only external model/Storage/project boundaries are simulated. They cover JSON/SSE
handled publication failures, report selection and preservation, download digest
checks, continuation/session handling, and resource cleanup. They do **not** prove
live Azure permissions, real search, cloud persistence, or a successful Blob export.

The repository's [cloud behavior contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/langgraph/responses/11-deep-agents/test-spec.yml)
checks delegated research, named revision, and publishing the original again. Its
sample-owned verifier downloads all three publications over HTTPS, verifies their
digests/attachment names, compares the original bytes before and after revision,
and re-downloads the original snapshot to establish immutability. Publication
errors cannot pass just because a response completed or mentioned a filename.
It deletes only observed report exports. The CI identity needs Blob deletion access
to the configured test container; no account keys are used. Stable CI agent names
reuse the same identity across runs to stay within the role-assignment limit.
Their two scoped Storage grants persist and are reused, not revoked when one job
finishes, because other runs or agent versions can still need them. Schema
validation alone does not execute this workflow.
For manual cloud acceptance, run the complete client, inspect
both reports and citations, verify that v1 remains unchanged, and repeat via the
Responses streaming API. Keep any SAS-bearing evidence private.

Stop test compute with `azd ai agent sessions list` and
`azd ai agent sessions stop <session-id>` when not using the demo client's cleanup.
Delete only your test exports. When retiring an agent that uses an existing
Storage account, first confirm that no other run or agent version still needs its
identity. Then run `python hooks/configure-report-storage.py --cleanup` from the
deployment workspace to remove only its recorded grants; pre-existing grants
are retained. Do not run role cleanup at the end of an ordinary CI job.
`azd down` removes azd-managed resources, **not**
the separately created report account; remove the dedicated report resource group
only after confirming it contains no resources you need to keep.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing report Storage configuration | Set `AZURE_STORAGE_ACCOUNT_NAME` and `AZURE_STORAGE_CONTAINER_NAME` in azd/CI; use `REPORT_STORAGE_*` in the standalone runtime `.env`. |
| Postdeploy role hook fails | Check the reported Azure error code, `AZURE_STORAGE_SUBSCRIPTION_ID`, the private container, and the deployer's role-assignment permission. An RBAC administrator can run the hook; do not ignore its failure. |
| Toolbox does not expose `web_search` | Confirm the Toolbox name, project, provisioned tool, and project/developer roles. |
| Publication returns a handled error / no download | Check the private container, network access, and the correct local or agent instance Blob grant. Do not fall back to account keys. |
| Download digest mismatch | Do not accept the file; republish the selected saved filename and retry. |
| A follow-up starts new research | Continue from the latest `response.id` and the same hosted `agent_session_id`; use `client.py` as the reference. |

## Next steps

- [Human-in-the-Loop](../07-human-in-the-loop/) for SDK mapping of LangGraph approval interrupts.
- [Files](../06-files/) for hosted session filesystem handling.
- [Observability](../08-observability/) for other tracing/exporter configurations.
- [Resilient Responses](../09-resilient/) for explicit durable background execution.

## Source examples

- [Merged LangChain Azure example (#1207)](https://github.com/langchain-ai/langchain-azure/pull/1207), used at commit `c480d810ca96e77860db64ba3403c3bf13d5dfcf`.
- [Official Deep Research example](https://github.com/langchain-ai/deepagents/tree/b6504f6654ee6f25e1cd923087291de9e51572cc/examples/deep_research), the original framework workflow.
