# What this sample demonstrates

Use the **LangChain Azure SDK with LangChain, LangGraph, and Deep Agents** to
research a topic, revise a saved report, and download both named versions from
private Azure Blob Storage. Run the same native graph locally or host it on
Microsoft Foundry over the **Responses protocol**.

The workflow reuses the [LangChain Azure Deep Research sample](https://github.com/langchain-ai/langchain-azure/tree/c480d810ca96e77860db64ba3403c3bf13d5dfcf/samples/hosting/langgraph-hosted-agents/responses/12_deep_agents),
adapted to this repository's `src/` layout, uv lock, inline Toolbox, and deployment
conventions. The SDK sample is based on LangChain's official Deep Research example;
named revisions and Blob publication extend its original research workflow.

## How it works

1. `create_deep_agent` plans work and delegates focused searches to
   `research-agent`. `AzureAIProjectToolbox` supplies `web_search`; a local
   `think_tool` records concise progress rather than private reasoning.
2. The coordinator saves `/report-v1.md`. Deep Agents' default `StateBackend`
   stores virtual files in conversation state; `FoundryCheckpointSaver` persists
   that state locally or in Foundry State Store when hosted.
3. A follow-up reads the original, saves `/report-v2.md`, edits that copy, and
   reads it back without replacing the original findings and citations.
4. `publish_report(report_name)` reads the selected saved file and uploads a new
   private Blob snapshot. It returns SHA256 and a one-hour, read-only HTTPS
   user-delegation SAS, never accepting model-supplied upload content or a destination.

[`agent.py`](src/langgraph-deep-agents/agent.py) assembles the native graph,
research subagent, and `TodoListMiddleware` independently of hosting.
[`main.py`](src/langgraph-deep-agents/main.py) owns `AzureAIOpenAIApiChatModel`,
the credential, default model clients, and saver until `ResponsesHostServer`
shuts down. [`report_export.py`](src/langgraph-deep-agents/report_export.py)
uses LangChain `ToolRuntime` to read conversation files. Blob is an export
destination, not a replacement filesystem or checkpointer.

### Configuration

| Variable | Purpose |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint; injected by Foundry/azd, set in `.env` for direct local execution. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment selected during initialization. |
| `TOOLBOX_NAME` | `deep-agents-tools`, declared in `azure.yaml`. |
| `AZURE_STORAGE_ACCOUNT_NAME` | azd/CI input: report Storage account name. |
| `AZURE_STORAGE_CONTAINER_NAME` | azd/CI input: private report container. |
| `REPORT_STORAGE_ACCOUNT_URL`, `REPORT_STORAGE_CONTAINER` | Runtime settings mapped from the two azd inputs; set directly in `.env` for manual execution. |

Both telemetry content-capture flags default to `false`. To opt in to content
recording, see the shared [tracing guide](../08-observability/). Queries still go
to the search service, and conversation checkpoints still contain report content.

## Prerequisites

1. **Python 3.13+** and [uv](https://docs.astral.sh/uv/getting-started/installation/)
   **0.11.7+** on `PATH`.
2. A Foundry project with a tool-capable model deployment and a Toolbox exposing
   `web_search`. Option 1 provisions and deploys these from `azure.yaml` if needed.
3. A dedicated Azure Storage account and private container. The manifest does
   **not** create them or grant Blob access; follow the setup below.
4. An authenticated Azure identity and the required permissions. Resource
   Contributor alone cannot assign roles; ask an RBAC administrator for missing grants.

| Identity / operation | Required access |
| --- | --- |
| Developer: project and Toolbox access | `Foundry User` on the Foundry project and Reader on its parent account. |
| Provisioner / deployer | Contributor on the resource group, `Foundry Project Manager` on an existing project, and the required Foundry role-assignment permissions when provisioning. |
| Project managed identity: managed tools | `Foundry User` on the parent Foundry account when not already provisioned. |
| Local developer and deployed agent: report publication | Each principal separately needs container-scoped `Storage Blob Data Contributor` and account-scoped `Storage Blob Delegator`. |

Foundry roles were previously named Azure AI User / Azure AI Project Manager;
their role IDs are unchanged. See the [hosted-agent permissions reference](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions).

Storage's delegation-key operation requires account-level scope; a data role on
only the container cannot sign download links. The developer, project identity,
and agent `instance_identity.principal_id` are different principals. Follow the
same [manual downstream-resource RBAC pattern](../../../agent-framework/responses/10-downstream-azure/#granting-the-agent-data-plane-access)
as the other Azure integration samples.

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
new ones. Run the following commands from this initialized project directory.

### Set up private report Storage

Use an existing private account/container, or create dedicated resources with
these Bash commands. Select the Storage subscription explicitly; it can differ
from the Foundry subscription in the same tenant. The resource creator needs
Contributor; the role assignments in the next step need an RBAC administrator.

```bash
export SUBSCRIPTION_ID="<storage-subscription-id>"
export LOCATION="<azure-region>"
export REPORT_RESOURCE_GROUP="<dedicated-report-resource-group>"
export REPORT_STORAGE_ACCOUNT="<globally-unique-storage-account>"
export REPORT_STORAGE_CONTAINER="reports"

az group create --subscription "$SUBSCRIPTION_ID" --name "$REPORT_RESOURCE_GROUP" --location "$LOCATION"
az storage account create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage container-rm create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --storage-account "$REPORT_STORAGE_ACCOUNT" --name "$REPORT_STORAGE_CONTAINER" --public-access off
azd env set AZURE_STORAGE_ACCOUNT_NAME "$REPORT_STORAGE_ACCOUNT"
azd env set AZURE_STORAGE_CONTAINER_NAME "$REPORT_STORAGE_CONTAINER"
```

With existing resources, skip creation and set the two azd values to their names.
Keep the Storage subscription and resource-group values for the role commands.
For direct local execution, `.env.example` uses the full account URL and container.

### Grant the local developer report access

An RBAC administrator runs the following for the identity actually used by
`DefaultAzureCredential`. These commands assume an interactive user; for CI or
another service principal, supply its object ID and use `ServicePrincipal`.

```bash
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
PRINCIPAL_TYPE="User"
REPORT_STORAGE_ID=$(az storage account show --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --query id -o tsv)
REPORT_CONTAINER_SCOPE="$REPORT_STORAGE_ID/blobServices/default/containers/$REPORT_STORAGE_CONTAINER"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" --role "Storage Blob Data Contributor" --scope "$REPORT_CONTAINER_SCOPE"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" --role "Storage Blob Delegator" --scope "$REPORT_STORAGE_ID"
```

PowerShell, using the same Storage values:

```powershell
$SUBSCRIPTION_ID = "<storage-subscription-id>"
$REPORT_RESOURCE_GROUP = "<report-resource-group>"
$REPORT_STORAGE_ACCOUNT = "<storage-account>"
$REPORT_STORAGE_CONTAINER = "reports"
azd env set AZURE_STORAGE_ACCOUNT_NAME $REPORT_STORAGE_ACCOUNT
azd env set AZURE_STORAGE_CONTAINER_NAME $REPORT_STORAGE_CONTAINER
$PRINCIPAL_ID = az ad signed-in-user show --query id -o tsv
$PRINCIPAL_TYPE = "User"
$REPORT_STORAGE_ID = az storage account show --subscription $SUBSCRIPTION_ID --resource-group $REPORT_RESOURCE_GROUP --name $REPORT_STORAGE_ACCOUNT --query id -o tsv
$REPORT_CONTAINER_SCOPE = "$REPORT_STORAGE_ID/blobServices/default/containers/$REPORT_STORAGE_CONTAINER"
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $PRINCIPAL_ID --assignee-principal-type $PRINCIPAL_TYPE --role "Storage Blob Data Contributor" --scope $REPORT_CONTAINER_SCOPE
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $PRINCIPAL_ID --assignee-principal-type $PRINCIPAL_TYPE --role "Storage Blob Delegator" --scope $REPORT_STORAGE_ID
```

If the administrator uses a different login, substitute the developer's object ID
rather than assigning access to the administrator. Wait for RBAC propagation.

### Provision and deploy the remote dependencies

```bash
azd provision
azd deploy --all
```

Skip provisioning when the project/model already exist. Deploying all services
creates the cloud Toolbox before the agent; local execution also needs that
Toolbox. Neither `azd provision` nor `azd ai agent run` deploys remote tools.
Blob roles remain an explicit setup step, not a deployment hook.

### Run the agent locally

```bash
azd ai agent run --no-client
```

The host listens on `http://localhost:8088`. Local execution still calls the cloud
model, Toolbox, and Blob account; it is not an offline mode.

### Invoke the local agent

In another terminal, from the initialized project directory:

```bash
azd ai agent invoke --local "Research LangGraph checkpoints. Cite primary sources, save report-v1.md, and give me a download link."
```

For the complete four-turn research/read/revise/download demo:

```bash
cd src/langgraph-deep-agents
uv sync --frozen
cp .env.example .env
uv run --frozen python client.py
```

Before running the client, fill in `.env` with the project endpoint, model,
Toolbox, and report account/container when those values are not already exported.

### Deploy to Foundry and grant the agent report access

After edits, run `azd deploy --all` again. The default is direct code deployment;
Docker is not required. The existing Dockerfile supports optional container deployment.
Retrieve the **deployed instance identity**, then have the Storage RBAC administrator
apply the same two roles used above to this principal:

```bash
PRINCIPAL_ID=$(azd ai agent show langgraph-deep-agents -o json | python -c 'import json,sys; print(json.load(sys.stdin)["instance_identity"]["principal_id"])')
PRINCIPAL_TYPE="ServicePrincipal"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" --role "Storage Blob Data Contributor" --scope "$REPORT_CONTAINER_SCOPE"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" --role "Storage Blob Delegator" --scope "$REPORT_STORAGE_ID"
```

```powershell
$PRINCIPAL_ID = (azd ai agent show langgraph-deep-agents -o json | ConvertFrom-Json).instance_identity.principal_id
$PRINCIPAL_TYPE = "ServicePrincipal"
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $PRINCIPAL_ID --assignee-principal-type $PRINCIPAL_TYPE --role "Storage Blob Data Contributor" --scope $REPORT_CONTAINER_SCOPE
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $PRINCIPAL_ID --assignee-principal-type $PRINCIPAL_TYPE --role "Storage Blob Delegator" --scope $REPORT_STORAGE_ID
```

Do not substitute the project identity or blueprint. Developer access does not
transfer to the hosted agent, and `azd deploy` does not configure these grants.
Recheck the principal after redeployment and allow time for role propagation.

### Invoke the deployed agent

```bash
azd ai agent invoke "Research LangGraph checkpoints, save report-v1.md, and give me a download link."
```

For the complete demo, set `FOUNDRY_PROJECT_ENDPOINT` in the runtime's `.env` to the
value from `azd env get-value FOUNDRY_PROJECT_ENDPOINT`, keep the report settings,
and run from `src/langgraph-deep-agents`:

```bash
uv run --frozen python client.py --agent-name langgraph-deep-agents
```

The client chains the latest response ID and deployed session ID, verifies both
download digests, and stops its returned test sessions. A publication failure
produces no invented download link; the saved report remains editable.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

Install [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
and sign in to Azure. Complete the remote model, Toolbox, private Storage, and
identity setup above before F5; Toolkit does not grant external Blob permissions.

### Set up the Python environment

Open this sample folder in VS Code. In its terminal:

```bash
cd src/langgraph-deep-agents
uv sync --frozen
cp .env.example .env
```

Fill in `.env` and select `src/langgraph-deep-agents/.venv` as the Python interpreter.
Toolkit generates `.vscode/launch.json` and `.vscode/tasks.json`; do not commit them.

### Run and debug the agent

Press **F5**; Agent Inspector opens automatically. Alternatively, run
`uv run --frozen python main.py`, then use **Foundry Toolkit: Open Agent Inspector**
to connect to `http://localhost:8088`. Use the same research prompt or run the demo
client in another terminal. No UI acceptance is implied by the offline tests.

### Deploy to Foundry

Use **Deploy Hosted Agent** for agent-only changes. When the Toolbox or Storage
configuration changes, run `azd deploy --all` from the initialized project and
recheck the deployed principal's Blob grants before invoking it.

## Reports, downloads, and privacy

Reports are virtual conversation files, not session filesystem attachments.
Checkpoints enable continuation of saved state, not arbitrary in-flight crash
recovery or permanent archival. Planning/search limits in prompts are guidance,
not hard execution limits.

Each publication creates a separate private Blob. Anyone holding its SAS URL can
read that one snapshot until expiry; there is no anonymous container access or
account-key fallback. Expiry **does not delete the Blob**. Keep transcripts, client
output, and SAS-bearing evidence private. Storage network restrictions still apply.

## Validation and cleanup

From `src/langgraph-deep-agents`:

```bash
uv run --frozen python -m unittest discover -s tests -v
```

Offline tests use the published SDK, native graph, and stock Responses host,
simulating external model, Storage, and project boundaries. They cover named
publication, report preservation, download digests, JSON/SSE failure handling,
continuation/session binding, and resource lifetimes; they do not prove live Azure access.

The [cloud test contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/langgraph/responses/11-deep-agents/test-spec.yml)
uses the existing runner for delegated research, named revision, and publication
URLs. It does **not** download files or compare their contents. CI requires its
actual deployed agent identity to have the two Blob roles before invocation;
missing access fails the publication assertions rather than silently skipping them.

For end-to-end acceptance, run `client.py` against the deployed agent, inspect
both downloaded reports and their citations, and confirm the original stays
unchanged. Retain the output as private evidence; a green schema check or offline
suite is not cloud acceptance.

The demo client stops its deployed test sessions. For other invocations, use
`azd ai agent sessions list` and `azd ai agent sessions stop <session-id>` as needed.
Delete only your report exports and local downloads after testing. Reuse shared
CI identity grants; revoke them only when retiring the identity and no other run
or version needs them. `azd down` does not delete the separately created report
account; remove dedicated resources only after confirming they are no longer needed.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing report Storage settings | Set the two `AZURE_STORAGE_*` azd values, or `REPORT_STORAGE_*` in the runtime's `.env`. |
| Toolbox not found | Run `azd deploy --all`; local execution still uses the cloud Toolbox. |
| Blob authorization failure | Check the actual caller's container data role, account delegation role, selected Storage subscription, and RBAC propagation. |
| Research succeeds but there is no download | The report stays editable; correct Blob access/network settings and request publication again. |
| Continuation loses the report | Use the latest response ID and, when hosted, the same deployed session; a new conversation starts empty. |

## Next steps

- Customize the research prompt or subagent in `research_agent/prompts.py` and `agent.py`.
- See [Human-in-the-loop](../07-human-in-the-loop/) and [Observability](../08-observability/).
- Read the [official Deep Research example](https://github.com/langchain-ai/deepagents/tree/b6504f6654ee6f25e1cd923087291de9e51572cc/examples/deep_research)
  for the upstream research workflow and the [SDK sample](https://github.com/langchain-ai/langchain-azure/pull/1207)
  for the selected Foundry adaptation.
