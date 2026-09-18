# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with **Retrieval Augmented Generation (RAG)** capabilities backed by **Azure AI Search**, hosted using the **Responses protocol**. The agent grounds its answers in product documentation by running a search against an Azure AI Search index before each model invocation, then citing the source in its response.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment.

### RAG via Azure AI Search

`AzureAISearchContextProvider` runs a search against the configured Azure AI Search index **before each model invocation** and injects the top results into the model context. The agent then composes a grounded answer and cites the source document.

See [main.py](src/agent-framework-agent-azure-search-rag-responses/main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4-mini`)
- An Azure AI Search service ([create one](https://learn.microsoft.com/azure/search/search-create-service-portal)).
  This sample uses an existing service; it does not declare the service in
  `azure.yaml`.
- Azure CLI logged in (`az login`)

### Required RBAC

The deployed agent's Managed Identity needs:

- **Azure AI User** on the Foundry project scope
- **Search Index Data Reader** on the Azure AI Search service (the sample only reads from the index)

The identity running the postprovision hook or fallback script needs:

- **Search Service Contributor** on the Azure AI Search service
- **Search Index Data Contributor** on the Azure AI Search service

## Provisioning the search index

The sample includes a top-level `postprovision` hook in `azure.yaml`. When
`AZURE_SEARCH_ENDPOINT` points to an existing Azure AI Search service, the hook
runs [`provision_index.py`](src/agent-framework-agent-azure-search-rag-responses/provision_index.py)
after `azd provision` and creates or seeds the `contoso-outdoors` index.
The search service itself remains a prerequisite and must be created
separately.

### Manual Python script (fallback)

Use the script directly for VS Code or other workflows that do not run the
`azd` hook. It creates the index (if it doesn't already exist) and seeds it
with the three Contoso Outdoors documents using `DefaultAzureCredential`. Your
identity needs the following roles on the **Azure AI Search service** scope:

- **Search Service Contributor** — to create the index
- **Search Index Data Contributor** — to upload documents

> Note: `Search Service Contributor` only covers control-plane operations (create/list/delete indexes). It does **not** grant document write access — `Search Index Data Contributor` is required for that even if you already have `Search Service Contributor`.

Grant the roles to your signed-in user (replace `<search-name>` and `<rg>`):

```powershell
$searchId = az search service show -n <search-name> -g <rg> --query id -o tsv
$me = az ad signed-in-user show --query id -o tsv

az role assignment create --assignee $me --role "Search Service Contributor"   --scope $searchId
az role assignment create --assignee $me --role "Search Index Data Contributor" --scope $searchId
```

Role propagation typically takes 1–5 minutes. Also confirm the search service has RBAC enabled (Portal → search service → **Keys** → **API Access control** → "Both" or "Role-based access control"); if it is set to "API Key" only, every AAD request returns `403 Forbidden`.

Then, from this directory:

```bash
export AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
export AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
python provision_index.py
```

Or in PowerShell:

```powershell
$env:AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
$env:AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
python provision_index.py
```

The script is safe to re-run: if the index already exists, it leaves the schema untouched and merges-or-uploads the documents. To change the schema, delete the index first (Azure AI Search does not allow modifying existing field attributes) and re-run the script.

### Index schema

| Field | Type | Attributes |
|---|---|---|
| `id` | `Edm.String` | key, filterable |
| `content` | `Edm.String` | searchable (full-text) |
| `sourceName` | `Edm.String` | retrievable, filterable |
| `sourceLink` | `Edm.String` | retrievable |

### Option B: Azure CLI + REST

```bash
SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
INDEX_NAME="contoso-outdoors"
TOKEN=$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)

# 1. Create the index.
curl -X PUT "$SEARCH_ENDPOINT/indexes/$INDEX_NAME?api-version=2024-07-01" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "contoso-outdoors",
    "fields": [
      { "name": "id",         "type": "Edm.String", "key": true,  "filterable": true,  "searchable": false, "retrievable": true },
      { "name": "content",    "type": "Edm.String", "key": false, "filterable": false, "searchable": true,  "retrievable": true, "analyzer": "standard.lucene" },
      { "name": "sourceName", "type": "Edm.String", "key": false, "filterable": true,  "searchable": false, "retrievable": true },
      { "name": "sourceLink", "type": "Edm.String", "key": false, "filterable": false, "searchable": false, "retrievable": true }
    ]
  }'

# 2. Upload three Contoso Outdoors documents matching the queries below.
curl -X POST "$SEARCH_ENDPOINT/indexes/$INDEX_NAME/docs/index?api-version=2024-07-01" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "value": [
      { "@search.action": "mergeOrUpload", "id": "return-policy",  "sourceName": "Contoso Outdoors Return Policy",     "sourceLink": "https://contoso.com/policies/returns",       "content": "Customers may return any item within 30 days of delivery. Items should be unused and include original packaging. Refunds are issued to the original payment method within 5 business days of inspection. As a thank you, every accepted return ships back with a complimentary Contoso TrailRunner sticker pack, item code TR-CANARY-7821." },
      { "@search.action": "mergeOrUpload", "id": "shipping-guide", "sourceName": "Contoso Outdoors Shipping Guide",    "sourceLink": "https://contoso.com/help/shipping",          "content": "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days within the continental United States. Expedited options are available at checkout. Use promo code SHIP-CANARY-4493 at checkout for a one-time free overnight upgrade on your first order." },
      { "@search.action": "mergeOrUpload", "id": "tent-care",      "sourceName": "TrailRunner Tent Care Instructions", "sourceLink": "https://contoso.com/manuals/trailrunner-tent", "content": "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow it to air dry completely before storage and avoid prolonged UV exposure to extend the lifespan of the waterproof coating. Replacement waterproofing kits are stocked under SKU TENT-CANARY-9067." }
    ]
  }'
```

You can also point the sample at any existing index that exposes a retrievable text field such as `content`.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the AI agent extension:
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
mkdir my-search-rag-agent && cd my-search-rag-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/11-azure-search-rag/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

The sample does not provision the Azure AI Search service. Create one first,
then set its endpoint. The index name defaults to `contoso-outdoors`:

```bash
azd env set AZURE_SEARCH_ENDPOINT "https://<your-search>.search.windows.net"
```

To use a different index name, set it before provisioning:

```bash
azd env set AZURE_SEARCH_INDEX_NAME "<your-index-name>"
```

If you don't already have a Foundry project and model deployment, provision
them:

```bash
azd provision
```

The registered `postprovision` hook creates or updates the search index during
this command. If `AZURE_SEARCH_INDEX_NAME` is not set, it defaults to
`contoso-outdoors`.

Run `azd provision` first so the hook has created and seeded the index.

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What is your return policy?"
```

Other examples:

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

The deployed agent's Managed Identity needs **Search Index Data Reader** on
the Azure AI Search service. The identity running the postprovision hook needs
**Search Service Contributor** and **Search Index Data Contributor** to create
and seed the index.

### Invoke the deployed agent

```bash
azd ai agent invoke "What is your return policy?"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  pipx install uv==0.11.7
  uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## How RAG works in this sample

`AzureAISearchContextProvider` runs a search against the configured Azure AI Search index **before each model invocation**. When the index is seeded with the three Contoso Outdoors documents from the provisioning section above:

| User query mentions | Search result injected |
|---|---|
| "return", "refund" | Contoso Outdoors Return Policy (canary token: `TR-CANARY-7821`) |
| "shipping", "promo" | Contoso Outdoors Shipping Guide (canary token: `SHIP-CANARY-4493`) |
| "tent", "fabric" | TrailRunner Tent Care Instructions (canary token: `TENT-CANARY-9067`) |

The model receives the top three search results as additional context and cites the source in its response. Each seeded document includes a unique `*-CANARY-*` token that does not exist in any model training data, so you can prove an answer was grounded in retrieved content (not fabricated from training) by asking for the canary and checking it appears in the response.

Replace the seed documents (or point the sample at an existing index with your own content) to ground the agent in your own knowledge base.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
