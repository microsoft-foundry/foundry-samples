# Hybrid Private Resources - Testing Guide

This guide covers testing Azure AI Foundry agents with tools that access private resources (AI Search, MCP servers, Fabric Data Agents). By default, the Foundry (AI Services) resource has **public network access disabled**. You can optionally [switch to public access](#switching-the-foundry-resource-to-public-access) for easier development.

> **Private Foundry (default):** You need a secure connection (VPN Gateway, ExpressRoute, or Azure Bastion) to reach the Foundry resource and run SDK tests. See [Connecting to a Private Foundry Resource](#connecting-to-a-private-foundry-resource).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Connecting to a Private Foundry Resource](#connecting-to-a-private-foundry-resource)
3. [Private MCP Evidence Checklist](#private-mcp-evidence-checklist)
4. [Switching the Foundry Resource to Public Access](#switching-the-foundry-resource-to-public-access)
5. [Step 1: Deploy the Template](#step-1-deploy-the-template)
6. [Step 2: Verify Private Endpoints](#step-2-verify-private-endpoints)
7. [Step 3: Create Test Data in AI Search](#step-3-create-test-data-in-ai-search)
8. [Step 4: Deploy MCP Server](#step-4-deploy-mcp-server)
9. [Step 5: Deploy OpenAPI Server](#step-5-deploy-openapi-server)
10. [Step 6: Configure A2A Connection](#step-6-configure-a2a-connection)
11. [Step 7: Configure Fabric Data Agent](#step-7-configure-fabric-data-agent)
12. [Step 8: Test via SDK](#step-8-test-via-sdk)
13. [Azure Functions Behind a VNet](#azure-functions-behind-a-vnet)
14. [Troubleshooting](#troubleshooting)
15. [Test Results Summary](#test-results-summary)

---

## Prerequisites

- Azure CLI installed and authenticated
- Owner or Contributor role on the subscription
- Python 3.10+ (for SDK testing)

---

## Connecting to a Private Foundry Resource

When the Foundry resource has public network access **disabled** (the default), you must connect to the Azure VNet before you can reach the Foundry endpoint for SDK testing or portal access.

Azure provides three methods:

| Method | Use Case |
|--------|----------|
| **Azure VPN Gateway** | Connect from your local machine/network over an encrypted tunnel |
| **Azure ExpressRoute** | Private, dedicated connection from on-premises infrastructure |
| **Azure Bastion** | Access a jump box VM on the VNet securely through the Azure portal |

For step-by-step setup instructions, see: [Securely connect to Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?view=foundry#securely-connect-to-foundry).

Once connected to the VNet, all SDK commands and portal interactions in this guide will work as documented.

---

## Private MCP Evidence Checklist

When troubleshooting private MCP connectivity, confirm the following. SDK test steps are in [Step 8: Test via SDK](#step-8-test-via-sdk).

### 1. Foundry configuration
- **Standard Agent** setup with network injection (`networkInjections.scenario='agent'`)
- **Agent Subnet** delegated to `Microsoft.App/environments` (one Foundry account per subnet)
- **Bring Your Own Virtual Network (BYO VNet)** — custom VNet support with subnet delegation

### 2. MCP hosting
- Container Apps environment created with `--internal-only true`
- Environment deployed on the **MCP Subnet** (`--infrastructure-subnet-resource-id`)
- Environment virtual IP is **internal** (static IP in the MCP Subnet range)
- Private DNS zone for the Container Apps domain is linked to the VNet
- App-level `--ingress external` reports `external=true` but is **not** internet-facing: the FQDN has no public DNS resolution, and the environment VIP remains in the MCP Subnet

### 3. Runtime

**MCP connectivity (direct HTTP)** — requires a secure connection (VPN Gateway, ExpressRoute, or Azure Bastion):

- Private DNS: `nslookup <mcp-server-fqdn>` resolves to the environment static IP
- `initialize` succeeds and returns `mcp-session-id`
- `tools/list` enumerates available tools
- `tools/call` executes a tool

Direct HTTP from the internet fails (no public DNS; no route to the internal VIP).

**MCP tool via agent (Data Proxy)** — if the Foundry resource has **public network access enabled**, SDK tests work from the internet without VPN/ExpressRoute/Bastion:

- Agent response includes `mcp_list_tools`
- Agent response includes `mcp_call`

The Data Proxy routes MCP traffic via the `scenario: 'agent'` network injection. Direct MCP connectivity still requires a VNet connection; the agent path does not.

---

## Switching the Foundry Resource to Public Access

If your security policy permits, you can enable public network access on the Foundry resource so that SDK tests and portal access work directly from the internet without VPN/ExpressRoute/Bastion.

In `modules-network-secured/ai-account-identity.bicep`, change:

```bicep
// Change from:
publicNetworkAccess: 'Disabled'
// To:
publicNetworkAccess: 'Enabled'

// Also change:
defaultAction: 'Deny'
// To:
defaultAction: 'Allow'
```

Then redeploy the template. Backend resources (AI Search, Cosmos DB, Storage) remain on private endpoints regardless of this setting.

To revert to private, set `publicNetworkAccess: 'Disabled'` and `defaultAction: 'Deny'`, then redeploy.

---

## Step 1: Deploy the Template

```bash
# Set variables
RESOURCE_GROUP="rg-hybrid-agent-test"
LOCATION="westus2"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Deploy the template
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file main.bicep \
  --parameters location=$LOCATION

# Get the deployment outputs
AI_SERVICES_NAME=$(az cognitiveservices account list -g $RESOURCE_GROUP --query "[0].name" -o tsv)
echo "AI Services: $AI_SERVICES_NAME"
```

---

## Step 2: Verify Private Endpoints

Confirm that backend resources have private endpoints:

```bash
# List private endpoints
az network private-endpoint list -g $RESOURCE_GROUP -o table

# Expected: Private endpoints for:
# - AI Search (*search-private-endpoint)
# - Cosmos DB (*cosmosdb-private-endpoint)
# - Storage (*storage-private-endpoint)
# - AI Services (*-private-endpoint)

# If public access is ENABLED, verify AI Services is publicly accessible:
AI_ENDPOINT=$(az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME --query "properties.endpoint" -o tsv)
curl -I $AI_ENDPOINT
# Should return HTTP 200 (accessible from internet)

# If public access is DISABLED (default), the curl above will fail.
# You must connect via VPN/ExpressRoute/Bastion to reach the endpoint.
# See: Connecting to a Private Foundry Resource
```

---

## Step 3: Create Test Data in AI Search

Since AI Search has a private endpoint, you need to access it from within the VNet or temporarily allow public access.

### Option A: Temporarily Enable Public Access on AI Search

```bash
AI_SEARCH_NAME=$(az search service list -g $RESOURCE_GROUP --query "[0].name" -o tsv)

# Temporarily enable public access
az search service update -g $RESOURCE_GROUP -n $AI_SEARCH_NAME \
  --public-network-access enabled

# Get admin key
ADMIN_KEY=$(az search admin-key show -g $RESOURCE_GROUP --service-name $AI_SEARCH_NAME --query "primaryKey" -o tsv)

# Create test index
curl -X POST "https://${AI_SEARCH_NAME}.search.windows.net/indexes?api-version=2023-11-01" \
  -H "Content-Type: application/json" \
  -H "api-key: ${ADMIN_KEY}" \
  -d '{
    "name": "test-index",
    "fields": [
      {"name": "id", "type": "Edm.String", "key": true},
      {"name": "content", "type": "Edm.String", "searchable": true}
    ]
  }'

# Add a test document
curl -X POST "https://${AI_SEARCH_NAME}.search.windows.net/indexes/test-index/docs/index?api-version=2023-11-01" \
  -H "Content-Type: application/json" \
  -H "api-key: ${ADMIN_KEY}" \
  -d '{
    "value": [
      {"@search.action": "upload", "id": "1", "content": "This is a test document for validating AI Search integration with Azure AI Foundry agents."}
    ]
  }'

# Disable public access again
az search service update -g $RESOURCE_GROUP -n $AI_SEARCH_NAME \
  --public-network-access disabled
```

---

## Step 4: Deploy MCP Server

Deploy an HTTP-based MCP server using the pre-built multi-auth MCP image.

> **Important**: Azure AI Agents require MCP servers that implement the **Streamable HTTP transport** (JSON-RPC over HTTP with session management). The multi-auth MCP server provides this with a `/noauth/mcp` endpoint for testing.

### 4.1 Import the Multi-Auth MCP Image

```bash
# Create ACR if needed
ACR_NAME="mcpacr$(date +%s | tail -c 5)"
az acr create --name $ACR_NAME --resource-group $RESOURCE_GROUP --sku Basic --location $LOCATION

# Import the pre-built multi-auth MCP image
az acr import \
  --name $ACR_NAME \
  --source retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env:latest \
  --image multi-auth-mcp:latest

# Create user-assigned identity with AcrPull role
az identity create --name mcp-identity --resource-group $RESOURCE_GROUP --location $LOCATION
IDENTITY_ID=$(az identity show --name mcp-identity -g $RESOURCE_GROUP --query "id" -o tsv)
IDENTITY_PRINCIPAL=$(az identity show --name mcp-identity -g $RESOURCE_GROUP --query "principalId" -o tsv)
ACR_ID=$(az acr show --name $ACR_NAME --query "id" -o tsv)
az role assignment create --assignee $IDENTITY_PRINCIPAL --role AcrPull --scope $ACR_ID

# Wait for role assignment to propagate
sleep 30
```

### 4.2 Create Container Apps Environment

```bash
VNET_NAME=$(az network vnet list -g $RESOURCE_GROUP --query "[0].name" -o tsv)
MCP_SUBNET_ID=$(az network vnet subnet show -g $RESOURCE_GROUP --vnet-name $VNET_NAME -n "mcp-subnet" --query "id" -o tsv)

# Create internal Container Apps environment
az containerapp env create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-env" \
  --location $LOCATION \
  --infrastructure-subnet-resource-id $MCP_SUBNET_ID \
  --internal-only true
```

### 4.3 Deploy the MCP Server

```bash
# Deploy container app with multi-auth MCP image
# Note: The image runs on port 8080
az containerapp create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-http-server" \
  --environment "mcp-env" \
  --image "${ACR_NAME}.azurecr.io/multi-auth-mcp:latest" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --user-assigned $IDENTITY_ID \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity $IDENTITY_ID

# Get the MCP server URL
MCP_FQDN=$(az containerapp show -g $RESOURCE_GROUP -n "mcp-http-server" --query "properties.configuration.ingress.fqdn" -o tsv)
echo "MCP Server URL: https://${MCP_FQDN}/noauth/mcp"
```

> **Note on `--ingress external`**: App-level `--ingress external` is external to the app within the Container Apps environment boundary. It does **not** create an internet-reachable endpoint when the environment is `--internal-only` and public network access is disabled. Internal Container Apps environments have no public endpoint — the FQDN only resolves within the VNet.

### 4.4 Configure Private DNS

```bash
MCP_STATIC_IP=$(az containerapp env show -g $RESOURCE_GROUP -n "mcp-env" --query "properties.staticIp" -o tsv)
DEFAULT_DOMAIN=$(az containerapp env show -g $RESOURCE_GROUP -n "mcp-env" --query "properties.defaultDomain" -o tsv)

# Create private DNS zone
az network private-dns zone create -g $RESOURCE_GROUP -n $DEFAULT_DOMAIN

# Link to VNet
VNET_ID=$(az network vnet show -g $RESOURCE_GROUP -n $VNET_NAME --query "id" -o tsv)
az network private-dns link vnet create \
  -g $RESOURCE_GROUP \
  -z $DEFAULT_DOMAIN \
  -n "containerapp-link" \
  -v $VNET_ID \
  --registration-enabled false

# Add wildcard A record
az network private-dns record-set a add-record -g $RESOURCE_GROUP -z $DEFAULT_DOMAIN -n "*" -a $MCP_STATIC_IP
```

### 4.5 (Optional) Deploy Public MCP Server for Testing

For easier testing without VNet constraints, you can also deploy a public MCP server:

```bash
# Create public Container Apps environment
az containerapp env create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-env-public" \
  --location $LOCATION

# Deploy public MCP server
az containerapp create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-http-server-public" \
  --environment "mcp-env-public" \
  --image "${ACR_NAME}.azurecr.io/multi-auth-mcp:latest" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --user-assigned $IDENTITY_ID \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity $IDENTITY_ID

# Get public MCP URL
PUBLIC_MCP_FQDN=$(az containerapp show -g $RESOURCE_GROUP -n "mcp-http-server-public" --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Public MCP Server URL: https://${PUBLIC_MCP_FQDN}/noauth/mcp"
```

---

## Step 5: Deploy OpenAPI Server

Deploy the calculator OpenAPI service on Container Apps for testing OpenAPI tool integration.

### 5.1 Build and Push the Image

```bash
# Build the OpenAPI server image
cd ../openapi-server
az acr build --registry $ACR_NAME --image openapi-server:latest .
cd ../tests
```

### 5.2 Deploy to Private Container Apps Environment

```bash
# Deploy to the existing private Container Apps environment (mcp-env)
az containerapp create \
  --resource-group $RESOURCE_GROUP \
  --name "openapi-server" \
  --environment "mcp-env" \
  --image "${ACR_NAME}.azurecr.io/openapi-server:latest" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --user-assigned $IDENTITY_ID \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity $IDENTITY_ID

# Get the private OpenAPI server URL
OPENAPI_FQDN=$(az containerapp show -g $RESOURCE_GROUP -n "openapi-server" --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Private OpenAPI Server URL: https://${OPENAPI_FQDN}"
```

### 5.3 (Optional) Deploy Public OpenAPI Server

```bash
az containerapp create \
  --resource-group $RESOURCE_GROUP \
  --name "openapi-server-public" \
  --environment "mcp-env-public" \
  --image "${ACR_NAME}.azurecr.io/openapi-server:latest" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --user-assigned $IDENTITY_ID \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity $IDENTITY_ID

PUBLIC_OPENAPI_FQDN=$(az containerapp show -g $RESOURCE_GROUP -n "openapi-server-public" --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Public OpenAPI Server URL: https://${PUBLIC_OPENAPI_FQDN}"
```

### 5.4 Verify Connectivity

```bash
# Test the health endpoint
curl -s "https://${OPENAPI_FQDN}/healthz"
# Expected: {"status":"ok"}

# Test the calculate endpoint
curl -s -X POST "https://${OPENAPI_FQDN}/calculate" \
  -H "Content-Type: application/json" \
  -d '{"operation":"add","a":2,"b":4}'
# Expected: {"operation":"add","a":2.0,"b":4.0,"result":6.0}
```

---

## Step 6: Configure A2A Connection

To test A2A (Agent-to-Agent) tool integration, you need a remote agent accessible via the A2A protocol.

### 6.1 Set Up a Remote A2A Agent

Deploy an A2A-compatible agent (e.g., another Foundry agent, or a custom A2A service) on the VNet or publicly. The agent must implement the [A2A protocol](https://a2a-protocol.org/latest/).

### 6.2 Create a Project Connection

In the Azure AI Foundry portal:

1. Navigate to your project → **Settings** → **Connections**
2. Click **+ New connection** → **Custom keys** (or **A2A** if available)
3. Set the **Target** URL to your remote agent's endpoint
4. Note the **Connection ID** for use in tests

### 6.3 Configure Environment

```bash
export A2A_CONNECTION_ID="<your-a2a-connection-id>"
# Optional: override the endpoint URL if the connection lacks a target
export A2A_ENDPOINT="https://<remote-agent-url>"
```

---

## Step 7: Configure Fabric Data Agent

To test Fabric Data Agent integration, you need a Microsoft Fabric workspace with a Data Agent connected to your Foundry project. You can test with a public workspace (no private endpoints) or a private workspace (with workspace-level private endpoints on your VNet).

### 7.1 Deploy a Fabric Capacity

A Fabric Capacity is an Azure resource (`Microsoft.Fabric/capacities`) that provides compute for Fabric workloads. The **F2 SKU** is the smallest (2 Capacity Units) and suitable for testing.

> **Important**: Deploy the Fabric Capacity in the **same region** as your VNet and AI Services deployment (e.g., `westus2`) for private endpoint connectivity.

#### Option A: Azure Portal

1. Go to the [Azure Portal](https://portal.azure.com) and search for **Microsoft Fabric**
2. Click **Create** and fill in:
   - **Subscription**: Your subscription
   - **Resource Group**: Your existing resource group (e.g., `rg-hybrid-agent-test`)
   - **Capacity Name**: A unique name (3–63 characters, lowercase, e.g., `fabriccaptest`)
   - **Region**: Same region as your deployment (e.g., `westus2`)
   - **Size**: **F2**
   - **Capacity Administrator**: Your email address
3. Click **Review + create** → **Create**

> **Note**: You may need to register the `Microsoft.Fabric` resource provider and request F2 quota in your subscription first:
> ```bash
> az provider register --namespace Microsoft.Fabric
> ```

#### Option B: Azure CLI / Bicep

```bash
# Deploy Fabric capacity via CLI
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-spec '
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "resources": [{
    "type": "Microsoft.Fabric/capacities",
    "apiVersion": "2023-11-01",
    "name": "fabriccaptest",
    "location": "[resourceGroup().location]",
    "sku": { "name": "F2", "tier": "Fabric" },
    "properties": {
      "administration": { "members": ["your-email@example.com"] }
    }
  }]
}'
```

Or add to your Bicep deployment:

```bicep
resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: 'fabriccaptest'
  location: location
  sku: {
    name: 'F2'
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: [ 'your-email@example.com' ]
    }
  }
}
```

### 7.2 Create a Fabric Workspace

1. Go to [https://app.fabric.microsoft.com/home](https://app.fabric.microsoft.com/home)
2. Click **Workspaces** → **New workspace**
3. Give the workspace a name (e.g., `agent-test-workspace`)
4. Under **Fabric and Power BI workspace types**, choose **Fabric**
5. Under **Details**, select the capacity you created in Step 7.1
6. Click **Apply**

### 7.3 Enable Private Endpoints (for VNet testing)

To test Fabric behind a VNet with private endpoints:

1. **Enable tenant setting** (requires Fabric Admin):
   - Go to [Fabric Admin Portal](https://app.fabric.microsoft.com/admin-portal) → **Tenant Settings**
   - Enable **"Configure workspace-level inbound network rules"**

2. **Deploy private endpoint for the Fabric workspace**:

   The `main.bicep` template already supports Fabric private endpoints via the `fabricWorkspaceResourceId` parameter. Redeploy with the workspace resource ID:

   ```bash
   # Get the Fabric workspace resource ID from the Azure Portal
   # (Azure Portal → Fabric workspace → Properties → Resource ID)

   az deployment group create \
     --resource-group $RESOURCE_GROUP \
     --template-file main.bicep \
     --parameters location=$LOCATION \
     --parameters fabricWorkspaceResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Fabric/capacities/<capacity>/workspaces/<workspace-id>"
   ```

   This creates a private endpoint for the Fabric workspace on the `pe-subnet` with a private DNS zone (`privatelink.fabric.microsoft.com`).

3. **Verify the private endpoint**:

   ```bash
   az network private-endpoint list -g $RESOURCE_GROUP --query "[?contains(name,'fabric')]" -o table
   ```

### 7.4 Add Foundry Project Identity to Workspace

1. In the [Fabric Portal](https://app.fabric.microsoft.com), open your workspace
2. Click **Manage access** (or **Settings** → **Access**)
3. Add your Foundry Project's managed identity as a **Contributor**

   To find the project identity:
   ```bash
   # Get the project's managed identity principal ID
   az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME \
     --query "identity.principalId" -o tsv
   ```

### 7.5 Create a Fabric Data Agent

1. In the Fabric Portal, navigate to your workspace
2. Click **+ New item** → **Data Agent** (or search for "Data Agent")
3. Configure the Data Agent with your Fabric data sources (e.g., lakehouse, warehouse, SQL endpoint)
4. Publish the Data Agent

### 7.6 Create a Project Connection

1. In the [Azure AI Foundry Portal](https://ai.azure.com), navigate to your project
2. Go to **Settings** → **Connections**
3. Click **+ New connection** → **Microsoft Fabric**
4. Configure the connection to point to your Fabric workspace and Data Agent
5. Note the **Connection ID** — you'll need it for the tests

### 7.7 Configure Environment

```bash
# For public Fabric workspace (no private endpoints)
export FABRIC_CONNECTION_ID_PUBLIC="<your-fabric-connection-id>"

# For private Fabric workspace (with private endpoints)
export FABRIC_CONNECTION_ID_PRIVATE="<your-private-fabric-connection-id>"

# Optional: Custom test query
export FABRIC_TEST_QUERY="What tables are available and what data do they contain?"
```

---

## Step 8: Test via SDK

Six test scripts are provided:

| Script | Description |
|--------|-------------|
| `test_agents_v2.py` | Full test suite: basic agent, AI Search, MCP, OpenAPI, A2A |
| `test_mcp_tools_agents_v2.py` | Focused MCP testing: connectivity + public/private agent tests |
| `test_ai_search_tool_agents_v2.py` | Focused AI Search testing |
| `test_openapi_tool_agents_v2.py` | Focused OpenAPI testing: connectivity + agent tests |
| `test_a2a_connector_agents_v2.py` | Focused A2A testing: connectivity + agent tests |
| `test_fabric_data_agent_v2.py` | Focused Fabric Data Agent testing: connectivity + agent tests |
| `test_azure_function_agents_v2.py` | Azure Function as OpenAPI tool: connectivity + agent tests |

### 8.1 Install Dependencies

```bash
pip install azure-ai-projects azure-identity openai
```

### 8.2 Configure Environment

```bash
# Set the project endpoint (get from Azure Portal -> AI Services -> Projects -> Properties)
export PROJECT_ENDPOINT="https://<ai-services>.services.ai.azure.com/api/projects/<project>"

# Optional: Override MCP server URLs
export MCP_SERVER_PUBLIC="https://<public-mcp-fqdn>/noauth/mcp"
export MCP_SERVER_PRIVATE="https://<private-mcp-fqdn>/noauth/mcp"

# Optional: OpenAPI server URL
export OPENAPI_SERVER_URL="https://<openapi-container-app-fqdn>"
export OPENAPI_SERVER_PUBLIC="https://<public-openapi-fqdn>"
export OPENAPI_SERVER_PRIVATE="https://<private-openapi-fqdn>"

# Optional: A2A connection
export A2A_CONNECTION_ID="<a2a-project-connection-id>"
export A2A_ENDPOINT="https://<remote-a2a-agent-url>"

# Optional: Fabric Data Agent connection
export FABRIC_CONNECTION_ID_PUBLIC="<public-fabric-connection-id>"
export FABRIC_CONNECTION_ID_PRIVATE="<private-fabric-connection-id>"

# Optional: Azure Function App
export FUNCTION_APP_PUBLIC="https://<func-app-name>.azurewebsites.net"
export FUNCTION_APP_PRIVATE="https://<private-func-app-name>.azurewebsites.net"
```

### 8.3 Run Full Test Suite

```bash
# Run all tests (basic agent, AI Search, MCP, OpenAPI, A2A)
python test_agents_v2.py

# Run specific test
python test_agents_v2.py --test basic_agent
python test_agents_v2.py --test ai_search
python test_agents_v2.py --test mcp_tool
```

### 8.4 Run MCP-Focused Tests

```bash
# Run all MCP tests (connectivity + public + private)
python test_mcp_tools_agents_v2.py

# Test only public MCP server
python test_mcp_tools_agents_v2.py --test public

# Test only private MCP server
python test_mcp_tools_agents_v2.py --test private

# With retries (useful for transient Hyena cluster routing issues)
python test_mcp_tools_agents_v2.py --test public --retry 3
```

### 8.5 Run OpenAPI-Focused Tests

```bash
# Run all OpenAPI tests (connectivity + agent tests)
python test_openapi_tool_agents_v2.py

# Test only public OpenAPI server
python test_openapi_tool_agents_v2.py --test public

# Test only private OpenAPI server
python test_openapi_tool_agents_v2.py --test private

# With retries
python test_openapi_tool_agents_v2.py --test public --retry 3
```

### 8.6 Run A2A-Focused Tests

```bash
# Run all A2A tests (connectivity + agent tests)
python test_a2a_connector_agents_v2.py

# Test only public A2A endpoint
python test_a2a_connector_agents_v2.py --test public

# Test only private A2A endpoint
python test_a2a_connector_agents_v2.py --test private

# With retries
python test_a2a_connector_agents_v2.py --retry 3
```

### 8.7 Run Fabric Data Agent Tests

```bash
# Run all Fabric tests (connectivity + public + private)
python test_fabric_data_agent_v2.py

# Test only public Fabric workspace
python test_fabric_data_agent_v2.py --test public

# Test only private Fabric workspace (VNet)
python test_fabric_data_agent_v2.py --test private

# With retries
python test_fabric_data_agent_v2.py --retry 3

# With a custom query
python test_fabric_data_agent_v2.py --test public --query "Show me the sales data summary"
```

### 8.8 Run Azure Function Tests

```bash
# Set Function App URLs
export FUNCTION_APP_PUBLIC="https://<func-app-name>.azurewebsites.net"
export FUNCTION_APP_PRIVATE="https://<func-app-name>.azurewebsites.net"

# Run all Function tests (connectivity + agent tests)
python test_azure_function_agents_v2.py

# Test only public Function App
python test_azure_function_agents_v2.py --test public

# Test only private Function App (VNet)
python test_azure_function_agents_v2.py --test private

# With retries
python test_azure_function_agents_v2.py --test private --retry 3
```

### 8.9 Understanding Test Results

**MCP Connectivity Test**: Direct HTTP test to verify the MCP server responds correctly. Requires a secure connection (VPN Gateway, ExpressRoute, or Azure Bastion) — see [Private MCP Evidence Checklist](#private-mcp-evidence-checklist).
- Sends `initialize` request and captures `mcp-session-id` header
- Sends `tools/list` to enumerate available tools
- Sends `tools/call` to execute the `add` tool

**MCP Tool via Agent Test**: Tests the full agent workflow:
- Creates an agent with MCP tool configuration
- Sends a request that triggers the MCP tool
- Validates the agent can call MCP tools through the Data Proxy
- If the Foundry resource has **public network access enabled**, this path works from the internet without VPN/ExpressRoute/Bastion

> **Known Issue**: Agent tests may fail ~50% of the time with `TaskCanceledException` due to Hyena cluster routing. The Data Proxy is only deployed on one of two scale units, and the load balancer routes in round-robin fashion. Use `--retry` to mitigate.

---

## Azure Functions Behind a VNet

> **Key concept**: "Azure Functions behind a VNet" does **not** mean Foundry or the model calls your function over your VNet. It means the Function App's own networking (inbound and/or outbound) is restricted to a customer-owned VNet. Foundry never directly invokes Azure Functions — the customer's application code executes the call.

### How It Works

An Azure Function runs inside a Function App, which is a specialized App Service. Networking is inherited from App Service networking primitives.

There are two **independent** networking dimensions:

| Dimension | Controls | Mechanism |
|-----------|----------|-----------|
| **Outbound** ("Where can my function call?") | Egress from the function runtime | **VNet Integration** — function is attached to a delegated subnet; all outbound traffic flows through it |
| **Inbound** ("Who can call my function?") | Access to the function endpoint | **Private Endpoint** — function gets a private IP in a subnet; public access can be disabled |

These combine into three distinct scenarios:

### The Three Scenarios

| Scenario | VNet Integration (outbound) | Private Endpoint (inbound) | `publicNetworkAccess` | DataProxy compatible? | Use case |
|----------|:--------------------------:|:--------------------------:|:---------------------:|:--------------------:|----------|
| **1. No VNet** | ❌ | ❌ | Enabled | ✅ Yes | Baseline — function can't reach private resources |
| **2. VNet Integration only** | ✅ | ❌ | Enabled | ✅ Yes | **Function reaches private resources** — the practical scenario for Foundry |
| **3. Full lockdown (VNet Integration + PE)** | ✅ | ✅ | Disabled | ❌ No | Customer code on VNet calls the function — DataProxy cannot |

#### Scenario 1: No VNet (Baseline)

The Function App has no VNet attachment. It can only reach public resources.

```
Agent → DataProxy → Function App (public) → ❌ private storage unreachable
```

The function's `storage.stored` field returns `false` — it can compute but can't reach private resources.

#### Scenario 2: VNet Integration Only (DataProxy-Compatible) ✅

The Function App has **VNet Integration** for outbound traffic but keeps `publicNetworkAccess: Enabled`. This is the practical scenario for Foundry OpenAPI tools.

```
Agent → DataProxy → Function App (public endpoint)
                         │
                         │  outbound via VNet Integration
                         ▼
                    Private Storage Account (no public endpoint)
                         └─ ✅ storage.stored = true
```

**Why this works**: The DataProxy can reach the Function via its public endpoint, and the Function can reach private resources via VNet Integration. The `storage.stored: true` field proves VNet Integration is working.

#### Scenario 3: Full Lockdown (Customer Code Only) 🔒

The Function App has both VNet Integration AND a Private Endpoint with `publicNetworkAccess: Disabled`. Only callers on the VNet can reach it.

```
Customer App (on VNet) → Function App (private endpoint)
                              │
                              │  outbound via VNet Integration
                              ▼
                         Private Storage Account
                              └─ ✅ storage.stored = true

Agent → DataProxy → Function App (public endpoint disabled)
                         └─ ❌ 403 Ip Forbidden
```

**Why the DataProxy can't use this**: The DataProxy resolves DNS at the Foundry infrastructure level, not through the VNet's private DNS zones. Even though the PE has a private IP, the DataProxy's traffic is not recognized as arriving via the PE. The Function App rejects it with `403 Ip Forbidden`.

**Contrast with Container Apps**: Internal Container Apps environments have no public endpoint at all — the private FQDN only resolves within the VNet, and the DataProxy reaches them natively via VNet routing. There is no `publicNetworkAccess` toggle.

**When to use Scenario 3**: When the Function is called by customer-owned compute (AKS, VM, App Service) that runs on the VNet — NOT via the Foundry DataProxy.

### What "Behind VNet" Does and Does Not Mean

| ✅ It means | ❌ It does NOT mean |
|------------|-------------------|
| The function can reach private resources via VNet Integration (outbound) | The function runs inside your VNet compute |
| Callers on the VNet can use Private Endpoint (inbound, Scenario 3) | Foundry DataProxy can use Private Endpoint (it cannot) |
| Storage writes go through the VNet to locked-down storage | Setting `publicNetworkAccess: Disabled` works with DataProxy |

### Relationship to Foundry Agents

```
Scenario 2 (DataProxy path):              Scenario 3 (Customer app path):

Model / Agent                              Model / Agent
   │                                          │
   │  tool call (JSON)                        │  tool call (JSON)
   ▼                                          ▼
DataProxy (Foundry infra)                  Customer App (AKS/VM)  ← runs in VNet
   │                                          │
   │  HTTPS to public endpoint                │  HTTPS via Private Endpoint
   ▼                                          ▼
Azure Function App                         Azure Function App
   │                                          │
   │  VNet Integration (outbound)             │  VNet Integration (outbound)
   ▼                                          ▼
Private Storage / DB / APIs                Private Storage / DB / APIs
```

### When Does the DataProxy Apply?

The DataProxy is **only** involved when Foundry-hosted infrastructure (Capability Hosts / Tool Server) needs to make outbound calls. This happens with:

- **Private OpenAPI tools** — Tool Server Python sandbox routes through DataProxy
- **Private MCP tools** — Tool Server C# connector routes through DataProxy
- **Private A2A tools** — Tool Server C# connector routes through DataProxy

If a Function is exposed as an **OpenAPI tool** (Scenario 2), the DataProxy routes the call to the Function's public endpoint. The Function then uses VNet Integration to reach private backends.

If the Function is called by customer application code (Scenario 3), the DataProxy is **not** in the path — the customer app calls the Function directly via its Private Endpoint on the VNet.

### Required Resources

| Resource | Scenario 2 | Scenario 3 | Purpose |
|----------|:----------:|:----------:|---------|
| Function App (EP1+ plan) | ✅ | ✅ | VNet Integration requires Elastic Premium |
| Storage Account | ✅ | ✅ | Required by Functions runtime |
| VNet + delegated subnet | ✅ | ✅ | For VNet Integration outbound |
| Storage PEs (Blob + Queue + File) | ✅ | ✅ | Runtime won't start without them when storage is locked |
| Storage DNS zones | ✅ | ✅ | `privatelink.blob`, `.queue`, `.file.core.windows.net` |
| Function App Private Endpoint | ❌ | ✅ | Inbound access from VNet callers |
| Function App DNS zone | ❌ | ✅ | `privatelink.azurewebsites.net` |

> ⚠️ **Storage requires three PEs**: Blob, Queue, **and File**. The File PE is often
> forgotten but is required for the Functions content share (`WEBSITE_CONTENTSHARE`).
> Without it, the runtime fails after storage lockdown.

### Deployment Order (Validated)

This sequence avoids the storage chicken-and-egg problem:

1. Create a **delegated subnet** for VNet Integration
2. Create a **Storage Account** with `defaultAction: Allow` (temporarily)
3. Create **Storage Private Endpoints** (Blob + Queue + File) with DNS zone groups
4. Create an **Elastic Premium (EP1)** plan
5. Create the **Function App** with VNet Integration (`--vnet`, `--subnet`)
6. Set app settings: `WEBSITE_CONTENTOVERVNET=1`, `WEBSITE_VNET_ROUTE_ALL=1`
7. **Deploy function code** with `func azure functionapp publish`
8. Verify the function (`curl /api/healthz` — check `private_storage.reachable`)
9. Lock down storage (`defaultAction: Deny`), then **restart the Function App**
10. Verify again (`curl /api/healthz` — storage should still be reachable via VNet)

> ⚠️ If storage is locked before the Function App is created, `az functionapp create`
> fails with `403 Forbidden` (cannot create file share). If storage is locked after
> deployment without restarting, the Function App may return `503 Application Error`.

### Testing an Azure Function Behind VNet with Foundry

The test proves VNet Integration by checking the `storage.stored` field:

- **Without VNet Integration** → `storage.stored: false` (can't reach private storage)
- **With VNet Integration** → `storage.stored: true` (VNet routes to private storage)

```bash
# Function WITHOUT VNet Integration (Scenario 1 — baseline)
export FUNCTION_APP_PUBLIC="https://<func-no-vnet>.azurewebsites.net"

# Function WITH VNet Integration (Scenario 2 — reaches private storage)
export FUNCTION_APP_PRIVATE="https://<func-with-vnet>.azurewebsites.net"

# Run tests
python test_azure_function_agents_v2.py --test all --retry 3
```

6. The DataProxy routes the OpenAPI tool call through the VNet, the same way it routes any private OpenAPI call. The agent creates an `OpenApiTool` pointing to the Function's spec, and the test validates the full round-trip.

> **Note**: The public and private URLs are typically the same because the Function App
> keeps `publicNetworkAccess: Enabled`. The "private" aspect is **outbound** — the function
> can reach private resources on the VNet that public functions cannot.

This follows the same pattern as the OpenAPI server tests (see [Step 5](#step-5-deploy-openapi-server)). A complete example is in [`azure-function-server/`](../azure-function-server/) with a README, Bicep template, and the function code.

---

## Troubleshooting

### Agent Can't Access AI Search

1. **Verify private endpoint exists**:
   ```bash
   az network private-endpoint list -g $RESOURCE_GROUP --query "[?contains(name,'search')]"
   ```

2. **Check Data Proxy configuration**:
   ```bash
   az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME \
     --query "properties.networkInjections"
   ```

3. **Verify AI Search connection in project**:
   - Go to the portal → Project → Settings → Connections
   - Confirm AI Search connection exists

### MCP Tool Fails with TaskCanceledException

This is a **known issue** with the Hyena cluster infrastructure:
- The Data Proxy is deployed on only **one of two scale units**
- The load balancer routes requests in **round-robin** fashion
- ~50% of requests hit the wrong scale unit and get `TaskCanceledException`

**Workaround**: Use `--retry` flag when running tests:
```bash
python test_mcp_tools_agents_v2.py --test public --retry 3
```

### MCP Tool Fails with 400 Bad Request

Check the error message for details:
- **404 Not Found**: Verify the MCP server URL includes the correct path (`/noauth/mcp`)
- **DNS resolution**: Ensure private DNS zone is configured correctly for Container Apps

### MCP Server Not Responding

1. **Check container app health**:
   ```bash
   az containerapp show -g $RESOURCE_GROUP -n "mcp-http-server" --query "properties.runningStatus"
   ```

2. **Check container logs**:
   ```bash
   az containerapp logs show -g $RESOURCE_GROUP -n "mcp-http-server" --tail 50
   ```

3. **Verify ingress port is 8080** (not 80):
   ```bash
   az containerapp ingress show -g $RESOURCE_GROUP -n "mcp-http-server" --query "targetPort"
   ```

### Fabric Data Agent Not Working

1. **Verify the project connection exists**:
   - Go to the Azure AI Foundry Portal → Project → Settings → Connections
   - Confirm a Microsoft Fabric connection exists and is active

2. **Verify the Foundry identity has access**:
   ```bash
   # Check the project's managed identity
   az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME \
     --query "identity.principalId" -o tsv
   ```
   Ensure this identity is a **Contributor** on the Fabric workspace.

3. **Verify the Fabric capacity is running**:
   - In the Azure Portal, check the Fabric capacity resource is in a running state
   - F2 capacities can be paused to save costs — ensure it's active during testing

4. **For private Fabric workspace — verify private endpoint**:
   ```bash
   az network private-endpoint list -g $RESOURCE_GROUP --query "[?contains(name,'fabric')]" -o table
   ```
   Ensure the private DNS zone `privatelink.fabric.microsoft.com` is linked to your VNet.

### Portal Shows "New Foundry Not Supported"

This is expected when network injection is configured. Use SDK testing instead - it works perfectly with network injection.

---

## Test Results Summary

### Test Scripts

| Script | Purpose |
|--------|---------|
| `test_agents_v2.py` | Full test suite: OpenAI API, basic agent, AI Search, MCP, OpenAPI, A2A |
| `test_mcp_tools_agents_v2.py` | Focused MCP testing with retry support |
| `test_ai_search_tool_agents_v2.py` | Focused AI Search testing |
| `test_openapi_tool_agents_v2.py` | Focused OpenAPI tool testing with retry support |
| `test_a2a_connector_agents_v2.py` | Focused A2A connector testing with retry support |
| `test_fabric_data_agent_v2.py` | Focused Fabric Data Agent testing with retry support |
| `test_azure_function_agents_v2.py` | Azure Function as OpenAPI tool, testing VNet routing |

### Validated ✅

| Test | Status | Notes |
|------|--------|-------|
| OpenAI Responses API (direct) | ✅ Pass | Works from anywhere |
| Basic Agent (no tools) | ✅ Pass | Works from anywhere |
| AI Search Tool | ✅ Pass | Data Proxy routes to private endpoint |
| MCP Connectivity (direct HTTP) | ✅ Pass | Server responds correctly |
| MCP Tool via Agent (public server) | ✅ Pass* | *~50% fail rate due to Hyena routing |
| MCP Tool via Agent (private server) | ✅ Pass* | *C# RemoteMcpConnector — VNet-aware |
| OpenAPI Connectivity (direct HTTP) | ✅ Pass | Both public and private servers |
| OpenAPI Tool via Agent (public) | ✅ Pass* | *~50% fail rate due to Hyena routing |
| OpenAPI Tool via Agent (private) | ✅ Pass* | *Requires DataProxy feature flags enabled |
| A2A Connectivity (direct HTTP) | ✅ Pass | Both public and private servers |
| A2A Tool via Agent (public) | ✅ Pass* | *C# RemoteA2AConnector — VNet-aware |
| A2A Tool via Agent (private) | ✅ Pass* | *C# RemoteA2AConnector — VNet-aware |
| Azure Function Connectivity | ✅ Pass | healthz + calculate endpoints |
| Azure Function as OpenAPI Tool | ✅ Pass* | *Function App must have `publicNetworkAccess: Enabled` |
| Fabric Connectivity (connection check) | 🔲 Pending | Requires Fabric workspace + connection |
| Fabric Data Agent via Agent (public) | 🔲 Pending | Requires Fabric capacity + Data Agent |
| Fabric Data Agent via Agent (private) | 🔲 Pending | Requires Fabric private endpoint |

### Known Limitations ⚠️

| Issue | Cause | Workaround |
|-------|-------|------------|
| ~50% TaskCanceledException | Hyena cluster has 2 scale units, Data Proxy only on 1 | Use `--retry` flag |
| Portal "New Foundry" blocked | Network injection not supported in portal | Use SDK testing |
| Function App `publicNetworkAccess: Disabled` → 403 | DataProxy resolves DNS at Foundry level, not via VNet PE | Keep `publicNetworkAccess: Enabled` (Scenario 2) |
| Function App 503 after storage lockdown | Runtime loses access to backing storage | Restart Function App; ensure Blob + Queue + **File** PEs all exist |
| Function App `storage.stored: false` with VNet | Missing File PE for content share | Add `file` PE alongside `blob` and `queue` PEs |

### Architecture Notes

1. **AI Search Tool works** because it uses Azure Private Endpoints with built-in DNS integration (`privatelink.search.windows.net`).

2. **MCP uses Streamable HTTP transport** - The multi-auth MCP server implements proper session management with `mcp-session-id` headers required by Azure's MCP client.

3. **OpenAPI tools** use the `OpenApiTool` with an inline OpenAPI spec. The Data Proxy routes to the private service the same way it routes MCP traffic — via the `scenario: 'agent'` network injection.

4. **A2A tools** use the `A2APreviewTool` which requires a project connection configured in the Foundry portal. The remote agent must implement the [A2A protocol](https://a2a-protocol.org/latest/).

5. **Fabric Data Agent tools** use the `MicrosoftFabricPreviewTool` (preview) which connects to a Microsoft Fabric workspace via a project connection. The Data Proxy routes requests to the Fabric Data Agent. For private workspaces, a private endpoint to `privatelink.fabric.microsoft.com` is required on the VNet.

6. **Container Apps require port 8080** - Both the MCP and OpenAPI server images run on port 8080, not 80.

6. **Use `/noauth/mcp` endpoint** for MCP testing without authentication. Production deployments should use `/mcp` with proper auth configuration.

7. **Azure Functions behind VNet** have three scenarios: (1) no VNet — baseline, (2) VNet Integration only — function reaches private resources, `publicNetworkAccess: Enabled`, DataProxy-compatible, (3) full lockdown with PE — `publicNetworkAccess: Disabled`, only VNet callers, NOT DataProxy-compatible. Scenario 2 is the practical choice for Foundry OpenAPI tools. Scenario 3 is for customer-owned code calling from the VNet.

8. **Container Apps vs Function Apps** have fundamentally different private networking. Internal Container Apps have no public endpoint — the DataProxy reaches them via VNet DNS natively. Function Apps with Private Endpoints still have a public hostname; `publicNetworkAccess: Disabled` blocks DataProxy traffic because it doesn't arrive via the PE NIC.

9. **Storage requires three PEs** for Functions behind VNet: Blob, Queue, **and File**. The File PE is required for the content share (`WEBSITE_CONTENTSHARE`). Without all three, the runtime fails after storage lockdown.

---

## Cleanup

```bash
# Delete all resources
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

> See [Account Deletion Prerequisites and Cleanup Guidance](../README.md#account-deletion-prerequisites-and-cleanup-guidance). The account capability host can remain in **Deleting** for approximately 20–30 minutes; wait until it is gone before reusing the Agent Subnet.
