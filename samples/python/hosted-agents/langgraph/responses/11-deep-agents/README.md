# LangGraph Deep Research Agent

This sample adapts LangChain's official [Build a deep research agent](https://docs.langchain.com/oss/python/deepagents/deep-research) tutorial to Microsoft Foundry hosting. The research workflow follows the tutorial, while the model, web search, durable checkpointing, and Responses protocol server use Microsoft Foundry.

## What the sample demonstrates

- Planning research with `TodoListMiddleware` and state-backed files.
- Delegating focused topics to a single `research-agent` subagent type.
- Discovering current sources with the managed `web_search` tool in a Foundry Toolbox.
- Producing a structured report with consolidated inline citations.
- Hosting the compiled Deep Agents graph through `ResponsesHostServer`.
- Persisting LangGraph checkpoints with `FoundryCheckpointSaver`.
- Publishing saved reports as private Azure Blob snapshots with read-only download links.

## How it works

The coordinator saves the request to `/research_request.md`, plans the work, and delegates research instead of searching directly. Research subagents use the tutorial's bounded search loop: two or three searches for simple questions and at most five for complex questions. The coordinator consolidates their citations, writes `/report-v1.md`, and verifies that the report covers the original request.

The agent uses a model deployed in the Foundry project. Its coordinator and research subagent share all tools loaded from the `deep-agents-tools` Toolbox. The Toolbox is declared as an `azure.ai.toolbox` service in `azure.yaml`, and the hosted agent lists it under `uses`, so `azd` deploys the Toolbox before the agent.

The coordinator also has `publish_report(report_name)`, adapted from the
[SDK sample's Blob publication tool](https://github.com/langchain-ai/langchain-azure/blob/c480d810ca96e77860db64ba3403c3bf13d5dfcf/samples/hosting/langgraph-hosted-agents/responses/12_deep_agents/report_export.py).
It reads the selected saved virtual file, uploads a separate private Blob, and
returns its SHA256 and a one-hour, read-only HTTPS user-delegation SAS. Working
files remain in the existing checkpoint-backed state for later edits; Blob is
an export destination, not a new filesystem or checkpointer.

## Project structure

The application follows the official Deep Research example's modular structure:

```text
src/langgraph-deep-agents/
├── main.py
├── agent.py
├── utils.py
├── report_export.py
└── research_agent/
    ├── __init__.py
    ├── prompts.py
    └── tools.py
```

- `main.py` owns the Foundry checkpoint, Responses server, and report-upload credential lifecycle.
- `agent.py` composes the coordinator, research subagent, and planning middleware.
- `utils.py` constructs the Foundry-backed chat model.
- `report_export.py` publishes a saved report without changing its working copy.
- `research_agent/prompts.py` contains the research workflow and delegation instructions.
- `research_agent/tools.py` loads the tools exposed by the Foundry Toolbox.

The extra `main.py` is the hosting adaptation that starts the Foundry Responses server, and `report_export.py` adds Blob publication. The existing model helper and research-module layout are preserved.

## Prerequisites

1. Install the [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd).
2. Install the Foundry agent extension with `azd extension install azure.ai.agents`.
3. Authenticate with `azd auth login`.
4. Install Python 3.13 or later.
5. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7
   or later and ensure it is available on `PATH`.
6. Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and
   authenticate with `az login` for the additional Storage setup below.

## Initialize and provision

```bash
mkdir hosted-langgraph-deep-agent && cd hosted-langgraph-deep-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/11-deep-agents/azure.yaml
```

### Configure private report Storage

The manifest does not create report Storage or grant external Blob permissions.
Use a dedicated private account/container, or create one with the Bash commands
below. Select the Storage subscription explicitly; it can differ from Foundry's
subscription in the same tenant. The resource creator needs Contributor, and an
administrator needs Owner or Role Based Access Control Administrator to assign roles.

```bash
SUBSCRIPTION_ID="<storage-subscription-id>"
LOCATION="<azure-region>"
REPORT_RESOURCE_GROUP="<dedicated-report-resource-group>"
REPORT_STORAGE_ACCOUNT="<globally-unique-storage-account>"
REPORT_STORAGE_CONTAINER="reports"
DEVELOPER_PRINCIPAL_ID="<local-developer-object-id>"

az group create --subscription "$SUBSCRIPTION_ID" --name "$REPORT_RESOURCE_GROUP" --location "$LOCATION"
az storage account create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage container-rm create --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --storage-account "$REPORT_STORAGE_ACCOUNT" --name "$REPORT_STORAGE_CONTAINER" --public-access off
azd env set AZURE_STORAGE_ACCOUNT_NAME "$REPORT_STORAGE_ACCOUNT"
azd env set AZURE_STORAGE_CONTAINER_NAME "$REPORT_STORAGE_CONTAINER"
REPORT_STORAGE_ID=$(az storage account show --subscription "$SUBSCRIPTION_ID" --resource-group "$REPORT_RESOURCE_GROUP" --name "$REPORT_STORAGE_ACCOUNT" --query id -o tsv)
REPORT_CONTAINER_SCOPE="$REPORT_STORAGE_ID/blobServices/default/containers/$REPORT_STORAGE_CONTAINER"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$DEVELOPER_PRINCIPAL_ID" --assignee-principal-type User --role "Storage Blob Data Contributor" --scope "$REPORT_CONTAINER_SCOPE"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$DEVELOPER_PRINCIPAL_ID" --assignee-principal-type User --role "Storage Blob Delegator" --scope "$REPORT_STORAGE_ID"
```

With existing Storage, skip the three resource-creation commands. Grant the
identity actually used by `DefaultAzureCredential`, not necessarily the
administrator running the commands. For an interactive developer, find its ID
with `az ad signed-in-user show --query id -o tsv`; for a service principal, use
its object ID and change `--assignee-principal-type` to `ServicePrincipal`.
The account-level delegation role is required to sign links; container-only data
access is insufficient. Allow time for RBAC propagation.

PowerShell equivalent for existing private Storage:

```powershell
$SUBSCRIPTION_ID = "<storage-subscription-id>"
$REPORT_RESOURCE_GROUP = "<report-resource-group>"
$REPORT_STORAGE_ACCOUNT = "<storage-account>"
$REPORT_STORAGE_CONTAINER = "reports"
$DEVELOPER_PRINCIPAL_ID = "<local-developer-object-id>"
azd env set AZURE_STORAGE_ACCOUNT_NAME $REPORT_STORAGE_ACCOUNT
azd env set AZURE_STORAGE_CONTAINER_NAME $REPORT_STORAGE_CONTAINER
$REPORT_STORAGE_ID = az storage account show --subscription $SUBSCRIPTION_ID --resource-group $REPORT_RESOURCE_GROUP --name $REPORT_STORAGE_ACCOUNT --query id -o tsv
$REPORT_CONTAINER_SCOPE = "$REPORT_STORAGE_ID/blobServices/default/containers/$REPORT_STORAGE_CONTAINER"
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $DEVELOPER_PRINCIPAL_ID --assignee-principal-type User --role "Storage Blob Data Contributor" --scope $REPORT_CONTAINER_SCOPE
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $DEVELOPER_PRINCIPAL_ID --assignee-principal-type User --role "Storage Blob Delegator" --scope $REPORT_STORAGE_ID
```

Then provision and deploy the existing Foundry services:

```bash
azd up
```

`azd up` provisions the Foundry project and model, then deploys the connection-free web-search Toolbox and hosted agent together. No external search API key is required.

## Run locally

```bash
azd ai agent run --no-client
```

In another terminal:

```bash
azd ai agent invoke --local "Compare the latest approaches to small language models on consumer devices and give me a download link for the report."
```

The local server also accepts Responses requests at `http://localhost:8088/responses`.

When running `python main.py` directly, set `REPORT_STORAGE_ACCOUNT_URL` and
`REPORT_STORAGE_CONTAINER` in `.env`, as shown in `.env.example`. `azd` maps them
from `AZURE_STORAGE_ACCOUNT_NAME` and `AZURE_STORAGE_CONTAINER_NAME` automatically.
Local runs still need the cloud model, deployed Toolbox, private container, and
the developer's separate Blob permissions.

## Deploy

```bash
azd deploy
```

Before hosted invocation, have the Storage administrator assign the same two
roles to the deployed agent's **instance identity**, separately from the developer:

```bash
AGENT_PRINCIPAL_ID=$(azd ai agent show langgraph-deep-agents -o json | python -c 'import json,sys; print(json.load(sys.stdin)["instance_identity"]["principal_id"])')
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$AGENT_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope "$REPORT_CONTAINER_SCOPE"
az role assignment create --subscription "$SUBSCRIPTION_ID" --assignee-object-id "$AGENT_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Storage Blob Delegator" --scope "$REPORT_STORAGE_ID"
```

```powershell
$AGENT_PRINCIPAL_ID = (azd ai agent show langgraph-deep-agents -o json | ConvertFrom-Json).instance_identity.principal_id
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $AGENT_PRINCIPAL_ID --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope $REPORT_CONTAINER_SCOPE
az role assignment create --subscription $SUBSCRIPTION_ID --assignee-object-id $AGENT_PRINCIPAL_ID --assignee-principal-type ServicePrincipal --role "Storage Blob Delegator" --scope $REPORT_STORAGE_ID
```

Do not grant the project's identity or blueprint instead. `azd deploy` does not
configure these external grants. Recheck the instance principal after deployment,
wait for propagation, and then invoke:

```bash
azd ai agent invoke "Research recent advances in small language models and give me a download link for the report."
```

See [Microsoft Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent) for the complete deployment workflow.

## Debug in VS Code

Open this sample folder in VS Code, run `uv sync --frozen` from `src/langgraph-deep-agents`, select `src/langgraph-deep-agents/.venv` as the Python interpreter, and create `.env` from `.env.example`. Press **F5** to start the server under `debugpy` and open Foundry Toolkit Agent Inspector.

Complete the model, Toolbox, private Storage, and developer Blob-access setup
before F5. The Toolkit does not grant external Storage permissions.

## Download and update reports

Open the returned URL in a browser, or download outside this checkout:

```bash
curl --fail --location "<download_url>" --output "/path/outside/repository/report.md"
```

Compare the downloaded file's SHA256 with the value returned by `publish_report`.
In the same conversation, ask the agent to read `/report-v1.md`, copy it to
`/report-v2.md`, and make the requested edits only to that copy. Ask it to read
both saved files and return clearly labeled download links for both versions.
Download both, compare each SHA256, and confirm the original file and its earlier
download remain unchanged. When calling the Responses API directly, carry the
latest response ID and the hosted session ID. Each publication creates a new
Blob; neither revising the copy nor publishing it overwrites the original.

Publication failures return no link and leave the saved report editable. Anyone
holding a valid SAS URL can read its snapshot until expiry. Expiry does **not**
delete the Blob; delete your test exports explicitly, and remove separately created
Storage resources when no longer needed. `azd down` does not own those resources.

Tool results now contain bearer download URLs. The sample therefore defaults both
telemetry content-capture flags to `false` before hosting. Keep URLs, transcripts,
and downloaded reports private; opting in to content capture can record them.

## Validate Blob publication

From `src/langgraph-deep-agents`:

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -v
```

The tests cover the added tool, credential lifetime, unchanged researcher tools,
report preservation, and native JSON/SSE publication success/failure. They use
the real `FoundryCheckpointSaver` with its local filesystem State Store backend,
including checkpoints created in the same second. SDK 1.2.12 or later is required
for checkpoint-ID ordering; `uv.lock` includes this fix. External model and Blob
boundaries are simulated; the original model helper and research tools are unchanged.

The cloud contract checks research, publication, revision of a separate saved copy,
and reading both versions using the existing test-spec schema. It does not download
the files. For full
acceptance, run against the deployed agent, download the original and revised
snapshots, compare their returned digests and contents, and re-download the old
URL to confirm it is unchanged. Schema/offline success is not cloud acceptance.
CI's deployed instance needs the same Blob roles; missing permission must fail,
not be bypassed with account keys. Retain shared CI grants until the identity is
retired and no other version or run needs them.
