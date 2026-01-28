# Hybrid Private Resources - Testing Guide

This guide covers testing Azure AI Foundry agents with tools that access private resources (AI Search, MCP servers) when the AI Services account has public access enabled.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Deploy the Template](#step-1-deploy-the-template)
3. [Step 2: Verify Private Endpoints](#step-2-verify-private-endpoints)
4. [Step 3: Create Test Data in AI Search](#step-3-create-test-data-in-ai-search)
5. [Step 4: Deploy MCP Server](#step-4-deploy-mcp-server)
6. [Step 5: Test via SDK](#step-5-test-via-sdk)
7. [Troubleshooting](#troubleshooting)
8. [Test Results Summary](#test-results-summary)

---

## Prerequisites

- Azure CLI installed and authenticated
- Owner or Contributor role on the subscription
- Python 3.10+ (for SDK testing)

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

Confirm that backend resources have private endpoints but AI Services does not:

```bash
# List private endpoints
az network private-endpoint list -g $RESOURCE_GROUP -o table

# Expected: Private endpoints for:
# - AI Search (*search-private-endpoint)
# - Cosmos DB (*cosmosdb-private-endpoint)
# - Storage (*storage-private-endpoint)
# - AI Services (*-private-endpoint) - for internal Data Proxy access

# Verify AI Services is publicly accessible
AI_ENDPOINT=$(az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME --query "properties.endpoint" -o tsv)
curl -I $AI_ENDPOINT
# Should return HTTP 200 (accessible from internet)
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

## Step 5: Test via SDK

Two test scripts are provided:

| Script | Description |
|--------|-------------|
| `test_agents_v2.py` | Full test suite: basic agent, AI Search, MCP tools |
| `test_mcp_tools_agents_v2.py` | Focused MCP testing: connectivity + public/private agent tests |

### 5.1 Install Dependencies

```bash
pip install azure-ai-projects azure-identity openai
```

### 5.2 Configure Environment

```bash
# Set the project endpoint (get from Azure Portal -> AI Services -> Projects -> Properties)
export PROJECT_ENDPOINT="https://<ai-services>.services.ai.azure.com/api/projects/<project>"

# Optional: Override MCP server URLs
export MCP_SERVER_PUBLIC="https://<public-mcp-fqdn>/noauth/mcp"
export MCP_SERVER_PRIVATE="https://<private-mcp-fqdn>/noauth/mcp"
```

### 5.3 Run Full Test Suite

```bash
# Run all tests (basic agent, AI Search, MCP)
python test_agents_v2.py

# Run specific test
python test_agents_v2.py --test basic_agent
python test_agents_v2.py --test ai_search
python test_agents_v2.py --test mcp_tool
```

### 5.4 Run MCP-Focused Tests

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

### 5.5 Understanding Test Results

**MCP Connectivity Test**: Direct HTTP test to verify the MCP server responds correctly:
- Sends `initialize` request and captures `mcp-session-id` header
- Sends `tools/list` to enumerate available tools
- Sends `tools/call` to execute the `add` tool

**MCP Tool via Agent Test**: Tests the full agent workflow:
- Creates an agent with MCP tool configuration
- Sends a request that triggers the MCP tool
- Validates the agent can call MCP tools through the Data Proxy

> **Known Issue**: Agent tests may fail ~50% of the time with `TaskCanceledException` due to Hyena cluster routing. The Data Proxy is only deployed on one of two scale units, and the load balancer routes in round-robin fashion. Use `--retry` to mitigate.

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

### Portal Shows "New Foundry Not Supported"

This is expected when network injection is configured. Use SDK testing instead - it works perfectly with network injection.

---

## Test Results Summary

### Test Scripts

| Script | Purpose |
|--------|---------|
| `test_agents_v2.py` | Full test suite: OpenAI API, basic agent, AI Search, MCP |
| `test_mcp_tools_agents_v2.py` | Focused MCP testing with retry support |

### Validated ✅

| Test | Status | Notes |
|------|--------|-------|
| OpenAI Responses API (direct) | ✅ Pass | Works from anywhere |
| Basic Agent (no tools) | ✅ Pass | Works from anywhere |
| AI Search Tool | ✅ Pass | Data Proxy routes to private endpoint |
| MCP Connectivity (direct HTTP) | ✅ Pass | Server responds correctly |
| MCP Tool via Agent (public server) | ✅ Pass* | *~50% fail rate due to Hyena routing |

### Known Limitations ⚠️

| Issue | Cause | Workaround |
|-------|-------|------------|
| ~50% TaskCanceledException | Hyena cluster has 2 scale units, Data Proxy only on 1 | Use `--retry` flag |
| Portal "New Foundry" blocked | Network injection not supported in portal | Use SDK testing |
| Private MCP via Data Proxy | DNS resolution issues for Container Apps | Use public MCP server |

### Architecture Notes

1. **AI Search Tool works** because it uses Azure Private Endpoints with built-in DNS integration (`privatelink.search.windows.net`).

2. **MCP uses Streamable HTTP transport** - The multi-auth MCP server implements proper session management with `mcp-session-id` headers required by Azure's MCP client.

3. **Container Apps require port 8080** - The multi-auth MCP image runs on port 8080, not 80.

4. **Use `/noauth/mcp` endpoint** for testing without authentication. Production deployments should use `/mcp` with proper auth configuration.

---

## Cleanup

```bash
# Delete all resources
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
