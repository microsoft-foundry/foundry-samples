# What this sample demonstrates

A support specialist agent with Retrieval Augmented Generation (RAG) backed by **Azure AI Search**, the **Azure AI Search RAG Agent (Responses Protocol)** sample shows how to ground agent answers in a real keyword-indexed knowledge base using `TextSearchProvider` over `Azure.Search.Documents` via [Agent Framework](https://github.com/microsoft/agent-framework).

## How It Works

The agent uses a `TextSearchProvider` wired to an `Azure.Search.Documents.SearchClient`. Before each model invocation the framework runs a full-text search against the configured Azure AI Search index, retrieves the top three matching documents, injects them as context for the LLM, and the model composes an answer grounded in the retrieved information, reducing hallucination and ensuring responses reflect the actual product documentation.

> [!IMPORTANT]
> The agent assumes the search index already exists and is populated. It does **not** create or seed the index at runtime. See [Provisioning the search index](#provisioning-the-search-index) below for a one-time setup script that creates `contoso-outdoors` and seeds it with three Contoso Outdoors documents (return policy, shipping guide, tent care).

> [!NOTE]
> Provisioning of the Foundry project, model deployment, and the Azure AI Search service is handled by the [`azd-ai-starter-basic`](https://github.com/Azure-Samples/azd-ai-starter-basic) template, which `azd ai agent init` pulls in automatically. The chat model under `resources:` in `azure.yaml` flows into the starter's `AI_PROJECT_DEPLOYMENTS` parameter, and the `kind: tool` `id: azure_ai_search` entry flows into `AI_PROJECT_DEPENDENT_RESOURCES` to provision the Azure AI Search service plus a project-scoped connection.

> [!IMPORTANT]
> The starter's Azure AI Search bicep currently requires a co-provisioned storage account, but `azd ai agent init` does not auto-prompt for storage. After running `azd ai agent init`, manually edit the generated `azure.yaml` and add a `storage` entry to the agent's `resources:` array so both resources get provisioned together. See [Provisioning workaround](#provisioning-workaround-storage-dependency) below.

See [Program.cs](src/azure-search-rag/Program.cs) for the full implementation.

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1 — `azd provision` can create them for you).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **Additional Azure resources:** an Azure AI Search service with a populated index. `azd provision` (Option 1) can create the search service; the index must exist before the first run — see [Provisioning the search index](#provisioning-the-search-index).

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Chat model deployment name. Declared in `azure.yaml`. |
| `AZURE_SEARCH_ENDPOINT` | Yes | Azure AI Search service endpoint. Derived from `AZURE_AI_SEARCH_SERVICE_NAME` (auto-injected by the starter) via the binding in `azure.yaml`. Set manually only when running without `azd`. |
| `AZURE_SEARCH_INDEX_NAME` | Yes | Search index name. Defaults to `contoso-outdoors`. **Must exist before the agent starts** (see [Provisioning the search index](#provisioning-the-search-index)). |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

When using `azd ai agent run`, these are handled automatically. For manual runs, set them in your shell — .NET does not read `.env` files natively.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir azure-search-rag-agent && cd azure-search-rag-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/azure-search-rag/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, model deployment, or Azure AI Search service, `azd provision` creates them all for you.

> If you already have a Foundry project, model deployment, and Azure AI Search service, add `-p <project-id> -d <deployment-name>` to `azd ai agent init` to target existing resources.

#### Provisioning workaround: storage dependency

The starter's Azure AI Search bicep module currently requires a co-provisioned storage account, but `azd ai agent init` only auto-prompts for `azure_ai_search` and `bing_grounding` tool resources. After running `init` and **before provisioning**, open the generated `azure.yaml` and add a `storage` entry to the agent service's `resources:` array so both resources get provisioned together:

```yaml
services:
  azure-search-rag:
    config:
      resources:
        - resource: azure_ai_search
          connectionName: search
        - resource: storage
          connectionName: storage
```

Tracking issue: [Azure-Samples/azd-ai-starter-basic — make storage optional in azure_ai_search.bicep or auto-prompt](https://github.com/Azure-Samples/azd-ai-starter-basic/issues).

### Provision Azure resources (if needed)

If you don't already have a Foundry project, model deployment, and Azure AI Search service (and after applying the storage workaround above):

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

> The search index must exist before the agent starts — see [Provisioning the search index](#provisioning-the-search-index).

### Invoke the local agent

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local "What is your return policy?"
```

```bash
azd ai agent invoke --local "How long does shipping take?"
azd ai agent invoke --local "How do I clean my tent?"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "What is your return policy?"
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Configure the agent: copy `.env.example` to `.env` and fill in the [required variables](#environment-variables) (including `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_INDEX_NAME`). The sample loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI so `DefaultAzureCredential` can authenticate the terminal process (the **F5** path reuses the Azure sign-in from the Foundry Toolkit, so it doesn't need a separate `az login`):

   ```bash
   az login
   ```

4. Start the agent (listens on `http://localhost:8088`):

   ```bash
   dotnet run
   ```

5. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Provisioning the search index

The agent reads from a pre-existing index. Provision it once, before the first run, with the script below. The script is idempotent: it skips creation if the index already exists, and skips seeding if the index already has documents.

### Required schema

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `Edm.String` | key, filterable |
| `content` | `Edm.String` | searchable |
| `sourceName` | `Edm.String` | filterable |
| `sourceLink` | `Edm.String` | (none) |

### Required search service authentication mode

The script and the agent runtime both authenticate to Azure AI Search via Entra ID (AAD) bearer tokens, **not** API keys. The search service must therefore have RBAC enabled. Services created before May 2024, or services explicitly provisioned with `disableLocalAuth=false` and `authOptions=null`, default to **API-key-only** auth and will return `403 Forbidden` to every AAD token regardless of RBAC role assignments.

Verify the current auth mode:

```bash
az search service show -g <rg> -n <search-service> \
  --query "{authOptions:authOptions, disableLocalAuth:disableLocalAuth}" -o json
```

The expected output is one of:

```json
{ "authOptions": { "aadOrApiKey": { "aadAuthFailureMode": "http403" } }, "disableLocalAuth": false }
```

or, for AAD-only:

```json
{ "authOptions": null, "disableLocalAuth": true }
```

If you see `"authOptions": null` together with `"disableLocalAuth": false`, RBAC is **off** and you must enable it before the script (or the agent) can authenticate. Flip the service to accept both AAD and API keys (safest, no breaking change for existing key consumers):

```bash
az search service update -g <rg> -n <search-service> \
  --auth-options aadOrApiKey --aad-auth-failure-mode http403
```

Or go AAD-only (rejects all API keys):

```bash
az search service update -g <rg> -n <search-service> --disable-local-auth true
```

Either change takes effect immediately on the control plane; allow ~1 minute for the data plane to pick it up.

### Required RBAC for the user running the script

Grant your user `Search Index Data Contributor` on the search service scope. This single role covers both index management (create) and document write (upload) for the bootstrap.

> [!IMPORTANT]
> Subscription `Owner`, `Contributor`, or `User Access Administrator` are **not sufficient on their own**. Those roles cover the management plane (deploy/scale/grant) but contain no `dataActions`, so REST calls to `/indexes/...` return `403`. The data-plane Search role must be granted explicitly even for subscription Owners.

```bash
SEARCH_ID=$(az search service show -g <rg> -n <search-service> --query id -o tsv)
USER_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id $USER_OID --assignee-principal-type User \
  --role "Search Index Data Contributor" --scope $SEARCH_ID
```

### Bash one-shot using authenticated `az rest`

```bash
SEARCH_ENDPOINT="https://<search-service>.search.windows.net"
INDEX_NAME="contoso-outdoors"

INDEX_SCHEMA=$(cat <<EOF
{
  "name": "$INDEX_NAME",
  "fields": [
    { "name": "id", "type": "Edm.String", "key": true, "filterable": true },
    { "name": "content", "type": "Edm.String", "searchable": true },
    { "name": "sourceName", "type": "Edm.String", "filterable": true },
    { "name": "sourceLink", "type": "Edm.String" }
  ]
}
EOF
)

# Create the index (idempotent: 201 on create, 204 on update)
az rest --method put --resource https://search.azure.com \
  --url "${SEARCH_ENDPOINT}/indexes/${INDEX_NAME}?api-version=2024-07-01" \
  --headers Content-Type=application/json --body "$INDEX_SCHEMA"

# Seed three Contoso Outdoors documents
az rest --method post --resource https://search.azure.com \
  --url "${SEARCH_ENDPOINT}/indexes/${INDEX_NAME}/docs/index?api-version=2024-07-01" \
  --headers Content-Type=application/json --body '{
    "value": [
      {
        "@search.action": "mergeOrUpload",
        "id": "return-policy",
        "sourceName": "Contoso Outdoors Return Policy",
        "sourceLink": "https://contoso.com/policies/returns",
        "content": "Customers may return any item within 30 days of delivery. Items should be unused and include original packaging. Refunds are issued to the original payment method within 5 business days of inspection."
      },
      {
        "@search.action": "mergeOrUpload",
        "id": "shipping-guide",
        "sourceName": "Contoso Outdoors Shipping Guide",
        "sourceLink": "https://contoso.com/help/shipping",
        "content": "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days within the continental United States. Expedited options are available at checkout."
      },
      {
        "@search.action": "mergeOrUpload",
        "id": "tent-care",
        "sourceName": "TrailRunner Tent Care Instructions",
        "sourceLink": "https://contoso.com/manuals/trailrunner-tent",
        "content": "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow it to air dry completely before storage and avoid prolonged UV exposure to extend the lifespan of the waterproof coating."
      }
    ]
  }'
```

### Required RBAC for the agent runtime

The hosted agent runs under its own managed identity. Grant that identity `Search Index Data Reader` on the search service scope so it can query the index at runtime:

```bash
# Look up the agent MI principal id from the deployed agent version.
MI=$(az rest --method get --resource https://ai.azure.com \
  --url "https://<account>.services.ai.azure.com/api/projects/<project>/agents/azure-search-rag?api-version=v1" \
  --query "versions.latest.instance_identity.principal_id" -o tsv)

az role assignment create --assignee-object-id $MI --assignee-principal-type ServicePrincipal \
  --role "Search Index Data Reader" --scope $SEARCH_ID
```

Wait ~3 minutes for AAD propagation before invoking the agent.

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
