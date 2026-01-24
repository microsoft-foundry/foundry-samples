# Hybrid Private Resources - Testing Guide

This guide covers testing Azure AI Foundry agents with tools that access private resources (AI Search, MCP servers) when the AI Services account has public access enabled.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Deploy the Template](#step-1-deploy-the-template)
3. [Step 2: Verify Private Endpoints](#step-2-verify-private-endpoints)
4. [Step 3: Create Test Data in AI Search](#step-3-create-test-data-in-ai-search)
5. [Step 4: Deploy MCP Server (Optional)](#step-4-deploy-mcp-server-optional)
6. [Step 5: Test via Portal](#step-5-test-via-portal)
7. [Step 6: Test via SDK](#step-6-test-via-sdk)
8. [Troubleshooting](#troubleshooting)

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

### Option A: Deploy a Jump Box (Recommended)

```bash
# Get VNet and subnet info
VNET_NAME=$(az network vnet list -g $RESOURCE_GROUP --query "[0].name" -o tsv)

# Create jump box
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name "jumpbox-vm" \
  --image Ubuntu2204 \
  --vnet-name $VNET_NAME \
  --subnet "pe-subnet" \
  --admin-username azureuser \
  --generate-ssh-keys \
  --assign-identity

# SSH into jump box and create index
# (See template 15 TESTING-GUIDE.md Step 4 for detailed index creation)
```

### Option B: Temporarily Enable Public Access on AI Search

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

## Step 4: Deploy MCP Server (Optional)

Deploy an HTTP-based MCP server to the private VNet. 

> **Important**: Azure AI Agents require MCP servers that implement the **Streamable HTTP transport** (JSON-RPC over HTTP). Standard stdio-based MCP servers (like `mcp/hello-world`) will NOT work.

### 4.1 Create Container Apps Environment

```bash
# Get MCP subnet resource ID
MCP_SUBNET_ID=$(az network vnet subnet show -g $RESOURCE_GROUP --vnet-name $VNET_NAME -n "mcp-subnet" --query "id" -o tsv)

# Create Container Apps environment (internal only)
az containerapp env create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-env" \
  --location $LOCATION \
  --infrastructure-subnet-resource-id $MCP_SUBNET_ID \
  --internal-only true
```

### 4.2 Deploy HTTP-based MCP Server

An HTTP-based MCP server is provided in `mcp-http-server/`. Deploy it:

```bash
# Build and deploy (requires ACR with managed identity access)
cd mcp-http-server

# Create ACR and build
ACR_NAME="mcpacr$(date +%s | tail -c 5)"
az acr create --name $ACR_NAME --resource-group $RESOURCE_GROUP --sku Basic --location $LOCATION
az acr build --registry $ACR_NAME --image mcp-hello-http:v1 --file Dockerfile .

# Create user-assigned identity with AcrPull role
az identity create --name mcp-identity --resource-group $RESOURCE_GROUP --location $LOCATION
IDENTITY_ID=$(az identity show --name mcp-identity -g $RESOURCE_GROUP --query "id" -o tsv)
IDENTITY_PRINCIPAL=$(az identity show --name mcp-identity -g $RESOURCE_GROUP --query "principalId" -o tsv)
ACR_ID=$(az acr show --name $ACR_NAME --query "id" -o tsv)
az role assignment create --assignee $IDENTITY_PRINCIPAL --role AcrPull --scope $ACR_ID

# Deploy container app
az containerapp create \
  --resource-group $RESOURCE_GROUP \
  --name "mcp-http-server" \
  --environment "mcp-env" \
  --image "${ACR_NAME}.azurecr.io/mcp-hello-http:v1" \
  --target-port 80 \
  --ingress internal \
  --min-replicas 1 \
  --user-assigned $IDENTITY_ID \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity $IDENTITY_ID
```

### 4.3 Configure Private DNS

```bash
# Get environment info
MCP_STATIC_IP=$(az containerapp env show -g $RESOURCE_GROUP -n "mcp-env" --query "properties.staticIp" -o tsv)
DEFAULT_DOMAIN=$(az containerapp env show -g $RESOURCE_GROUP -n "mcp-env" --query "properties.defaultDomain" -o tsv)
MCP_FQDN=$(az containerapp show -g $RESOURCE_GROUP -n "mcp-http-server" --query "properties.configuration.ingress.fqdn" -o tsv)

echo "MCP FQDN: $MCP_FQDN"
echo "Static IP: $MCP_STATIC_IP"

# Create private DNS zone for Container Apps
az network private-dns zone create -g $RESOURCE_GROUP -n $DEFAULT_DOMAIN

# Link to VNet
VNET_ID=$(az network vnet show -g $RESOURCE_GROUP -n $VNET_NAME --query "id" -o tsv)
az network private-dns link vnet create \
  -g $RESOURCE_GROUP \
  -z $DEFAULT_DOMAIN \
  -n "containerapp-link" \
  -v $VNET_ID \
  --registration-enabled false

# Add A records
az network private-dns record-set a add-record -g $RESOURCE_GROUP -z $DEFAULT_DOMAIN -n "mcp-http-server" -a $MCP_STATIC_IP
az network private-dns record-set a add-record -g $RESOURCE_GROUP -z $DEFAULT_DOMAIN -n "*" -a $MCP_STATIC_IP
```

### 4.4 Test MCP with REST API

```python
import requests
from azure.identity import DefaultAzureCredential
import time

credential = DefaultAzureCredential()
token = credential.get_token("https://ai.azure.com/.default")

endpoint = "https://<ai-services>.services.ai.azure.com/api/projects/<project>"
api_version = "2025-05-15-preview"
mcp_url = "https://mcp-http-server.<default-domain>"

headers = {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}

# Create agent with MCP tool
agent_payload = {
    "model": "gpt-4o-mini",
    "name": "mcp-test-agent",
    "instructions": "Use the hello tool to greet users.",
    "tools": [{"type": "mcp", "server_label": "helloworld", "server_url": mcp_url}]
}
resp = requests.post(f"{endpoint}/assistants?api-version={api_version}", headers=headers, json=agent_payload)
agent = resp.json()
print(f"Agent: {agent['id']}")
```

---

## Step 5: Test via Portal

> **Note**: Portal testing may be blocked even with public access enabled if your deployment uses network injection (`networkInjections` property). In this case, use SDK testing (Step 6) instead.

### 5.1 Check if Portal Works

1. Navigate to [Azure AI Foundry portal](https://ai.azure.com)
2. Sign in with your Azure credentials
3. Toggle **"New Foundry"** ON (top right)
4. Select your project

If you see this error:
> "Your current setup uses a project, resource, region, custom domain, or disabled public network access that isn't supported in the new Foundry experience yet."

This is expected if network injection is configured. Use SDK testing instead.

### 5.2 Create an Agent with AI Search Tool (if portal works)

1. Go to **Agents** in the left menu
2. Click **+ New agent**
3. Configure the agent:
   - **Name**: `search-test-agent`
   - **Model**: `gpt-4o-mini`
   - **Instructions**: `You are a helpful assistant. Use the search tool to find information when asked.`
4. Add a tool:
   - Click **+ Add tool**
   - Select **Azure AI Search**
   - Choose the AI Search connection created by the deployment
   - Select `test-index`
5. **Save** the agent

### 5.3 Test the Agent

1. Open the agent in the playground
2. Send a message: `Search for information about AI Foundry agents`
3. Verify the agent uses the AI Search tool and returns results from the private index

**What this proves:**
- The agent (running in the cloud) can reach the private AI Search via the Data Proxy
- The Data Proxy correctly routes through the VNet to the private endpoint

### 5.4 Create an Agent with MCP Tool (If MCP Deployed)

1. Create a new agent
2. Add an MCP tool:
   - **Server URL**: `https://<mcp-server-fqdn>`
   - **Server Label**: `test-mcp`
3. Test that the agent can discover and use tools from the MCP server

---

## Step 6: Test via SDK

For automated testing or CI/CD pipelines, use the SDK:

### 6.1 Install Dependencies

```bash
pip install azure-ai-projects azure-ai-agents azure-identity
```

### 6.2 Run Test Script

Use the included `test_agents_v2.py` script or the following code:

```python
#!/usr/bin/env python3
"""Test agent with AI Search tool on private endpoint."""

import os
import time
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchTool
from azure.identity import DefaultAzureCredential

# Configuration - use project-scoped endpoint
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://<ai-services-name>.services.ai.azure.com/api/projects/<project-name>"
)
AI_SEARCH_CONNECTION = os.environ.get("AI_SEARCH_CONNECTION", "<connection-name>")
AI_SEARCH_INDEX = os.environ.get("AI_SEARCH_INDEX", "test-index")

def main():
    client = AIProjectClient(
        credential=DefaultAzureCredential(),
        endpoint=PROJECT_ENDPOINT,
    )
    print(f"Connected to: {PROJECT_ENDPOINT}")
    
    # Create AI Search tool using the SDK class (NOT dict format)
    search_tool = AzureAISearchTool(
        index_connection_id=AI_SEARCH_CONNECTION,
        index_name=AI_SEARCH_INDEX
    )
    
    # Create agent with AI Search tool
    agent = client.agents.create_agent(
        model="gpt-4o-mini",
        name="sdk-search-agent",
        instructions="Search for information when asked.",
        tools=search_tool.definitions,
        tool_resources=search_tool.resources
    )
    print(f"Created agent: {agent.id}")
    
    # Create thread and test
    thread = client.agents.threads.create()
    client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="Search for documents about AI Foundry"
    )
    
    run = client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
    print(f"Started run: {run.id}")
    
    # Wait for completion
    while run.status in ["queued", "in_progress"]:
        time.sleep(2)
        run = client.agents.runs.get(thread_id=thread.id, run_id=run.id)
        print(f"Status: {run.status}")
    
    if run.status == "completed":
        messages = client.agents.messages.list(thread_id=thread.id)
        for msg in messages:
            if msg.role == "assistant":
                for content in msg.content:
                    if hasattr(content, 'text'):
                        print(f"Response: {content.text.value}")
                break
        print("✓ Test passed!")
    else:
        print(f"✗ Run failed: {run.status}")
    
    # Cleanup
    client.agents.delete_agent(agent.id)
    print("Agent cleaned up")

if __name__ == "__main__":
    main()
```

### 6.3 Find Your Connection Name

```bash
# List connections in your project
az rest --method GET \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<ai-services>/projects/<project>/connections?api-version=2025-06-01" \
  --query "value[?properties.category=='CognitiveSearch'].name" -o tsv
```

---

## Troubleshooting

### Portal Shows "New Foundry Not Supported"

This error can occur even with public access enabled if **network injection** is configured:

```bash
# Check for network injection
az cognitiveservices account show -g $RESOURCE_GROUP -n $AI_SERVICES_NAME \
  --query "properties.networkInjections"
```

If you see `networkInjections` with a subnet configured, the portal's "New Foundry" experience won't work. **Use SDK testing instead** - it works perfectly with network injection.

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

### MCP Server Not Accessible

1. **Check private DNS zone**:
   ```bash
   az network private-dns record-set list -g $RESOURCE_GROUP -z $DEFAULT_DOMAIN
   ```

2. **Verify Container App is running**:
   ```bash
   az containerapp show -g $RESOURCE_GROUP -n "mcp-test-server" --query "properties.runningStatus"
   ```

---

## Cleanup

```bash
# Delete all resources
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
