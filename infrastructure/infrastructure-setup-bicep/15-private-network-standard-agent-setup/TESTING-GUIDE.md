# Private Network Setup Testing Guide

This guide walks through testing the Azure AI Foundry Agent Service with private network isolation, including integration with Azure AI Search, Microsoft Fabric, and MCP Remote Servers behind a VNet.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Create Resource Group](#step-1-create-resource-group)
3. [Step 2: Deploy the Bicep Template](#step-2-deploy-the-bicep-template)
4. [Step 3: Verify Deployment](#step-3-verify-deployment)
5. [Step 4: Test Azure AI Search Integration](#step-4-test-azure-ai-search-integration)
6. [Step 5: Test Microsoft Fabric Integration](#step-5-test-microsoft-fabric-integration)
7. [Step 6: Test MCP Remote Servers on VNet](#step-6-test-mcp-remote-servers-on-vnet)
8. [Cleanup](#cleanup)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Azure Access Requirements

- **Azure Subscription** with the following permissions:
  - **Azure AI Account Owner**: Create cognitive services account and project
  - **Owner or Role Based Access Administrator**: Assign RBAC to resources (Cosmos DB, Azure AI Search, Storage)
  - **Azure AI User**: Create and edit agents

### Register Resource Providers

Ensure the following providers are registered in your subscription:

```bash
az provider register --namespace 'Microsoft.KeyVault'
az provider register --namespace 'Microsoft.CognitiveServices'
az provider register --namespace 'Microsoft.Storage'
az provider register --namespace 'Microsoft.Search'
az provider register --namespace 'Microsoft.Network'
az provider register --namespace 'Microsoft.App'
az provider register --namespace 'Microsoft.ContainerService'
az provider register --namespace 'Microsoft.Fabric'  # If testing Fabric integration
```

### Tools Required

- Azure CLI (latest version)
- Access to a VM, VPN, or ExpressRoute for secure access to the VNet (required for testing)

---

## Step 1: Create Resource Group

Create a new resource group for your test deployment:

```bash
# Login to Azure (if needed)
az login

# Set your subscription
az account set --subscription "<your-subscription-id>"

# Create resource group
az group create --name "rg-private-network-test" --location "norwayeast"
```

**Supported Regions:**
- Class A subnet support (GA): Australia East, Brazil South, Canada East, East US, East US 2, France Central, Germany West Central, Italy North, Japan East, South Africa North, South Central US, South India, Spain Central, Sweden Central, UAE North, UK South, West Europe, West US, West US 3
- Class B and C subnet support (GA): All regions supported by Azure AI Foundry Agent Service

---

## Step 2: Deploy the Bicep Template

### Option A: Deploy with New Resources (Simplest)

This creates all resources (VNet, Cosmos DB, AI Search, Storage) automatically:

```bash
cd infrastructure/infrastructure-setup-bicep/15-private-network-standard-agent-setup

az deployment group create \
  --resource-group "rg-private-network-test" \
  --template-file main.bicep \
  --parameters location="norwayeast"
```

### Option B: Deploy with Existing VNet

If you have an existing VNet with pre-configured subnets:

```bash
az deployment group create \
  --resource-group "rg-private-network-test" \
  --template-file main.bicep \
  --parameters location="norwayeast" \
  --parameters existingVnetResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet-name>" \
  --parameters agentSubnetName="agent-subnet" \
  --parameters agentSubnetPrefix="192.168.0.0/24" \
  --parameters peSubnetName="pe-subnet" \
  --parameters peSubnetPrefix="192.168.1.0/24"
```

### Option C: Deploy with Existing Resources + Fabric

For testing with existing Azure AI Search, Storage, Cosmos DB, and Microsoft Fabric:

```bash
az deployment group create \
  --resource-group "rg-private-network-test" \
  --template-file main.bicep \
  --parameters location="norwayeast" \
  --parameters aiSearchResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Search/searchServices/<search-name>" \
  --parameters azureStorageAccountResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage-name>" \
  --parameters azureCosmosDBAccountResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.DocumentDB/databaseAccounts/<cosmos-name>" \
  --parameters fabricWorkspaceResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Fabric/capacities/<fabric-capacity-name>"
```

### Deployment Parameters Reference

| Parameter | Description | Default |
|-----------|-------------|---------|
| `location` | Azure region | `eastus2` |
| `aiServices` | Base name for AI Services | `aiservices` |
| `modelName` | Model to deploy | `gpt-4o` |
| `modelCapacity` | TPM capacity | `30` |
| `vnetName` | VNet name | `agent-vnet-test` |
| `agentSubnetName` | Agent subnet name | `agent-subnet` |
| `peSubnetName` | Private endpoint subnet | `pe-subnet` |
| `existingVnetResourceId` | Existing VNet resource ID | `""` (creates new) |
| `aiSearchResourceId` | Existing AI Search resource ID | `""` (creates new) |
| `azureStorageAccountResourceId` | Existing Storage resource ID | `""` (creates new) |
| `azureCosmosDBAccountResourceId` | Existing Cosmos DB resource ID | `""` (creates new) |
| `fabricWorkspaceResourceId` | Existing Fabric workspace ID | `""` (skips Fabric) |

---

## Step 3: Verify Deployment

### 3.1 Check Deployment Status

```bash
az deployment group show \
  --resource-group "rg-private-network-test" \
  --name "main" \
  --query "properties.provisioningState"
```

### 3.2 List Created Resources

```bash
az resource list \
  --resource-group "rg-private-network-test" \
  --output table
```

### 3.3 Verify Private Endpoints

```bash
az network private-endpoint list \
  --resource-group "rg-private-network-test" \
  --output table
```

Expected private endpoints:
- AI Services Account (`*-private-endpoint`)
- AI Search (`*search-private-endpoint`)
- Storage Account (`*storage-private-endpoint`)
- Cosmos DB (`*cosmosdb-private-endpoint`)
- Fabric (if configured) (`*-fabric-private-endpoint`)

### 3.4 Verify Private DNS Zones

```bash
az network private-dns zone list \
  --resource-group "rg-private-network-test" \
  --output table
```

Expected DNS zones:
- `privatelink.services.ai.azure.com`
- `privatelink.openai.azure.com`
- `privatelink.cognitiveservices.azure.com`
- `privatelink.search.windows.net`
- `privatelink.blob.core.windows.net`
- `privatelink.documents.azure.com`
- `privatelink.analysis.windows.net` (if Fabric configured)

---

## Step 4: Test Azure AI Search Integration

### 4.1 Access the Environment

Since all resources are behind private endpoints, you must access from within the VNet:

**Option 1: Deploy a Jump Box VM**
```bash
az vm create \
  --resource-group "rg-private-network-test" \
  --name "jumpbox-vm" \
  --image Ubuntu2204 \
  --vnet-name "<your-vnet-name>" \
  --subnet "<pe-subnet-name>" \
  --admin-username azureuser \
  --generate-ssh-keys
```

**Option 2: Use Azure Bastion** (recommended for production)

**Option 3: VPN/ExpressRoute** (enterprise setup)

### 4.2 Test AI Search Connectivity

From the jump box or VPN-connected machine:

```bash
# Get AI Search endpoint
AI_SEARCH_NAME=$(az search service list -g "rg-private-network-test" --query "[0].name" -o tsv)

# Test DNS resolution (should resolve to private IP)
nslookup ${AI_SEARCH_NAME}.search.windows.net

# Test connectivity
curl -I https://${AI_SEARCH_NAME}.search.windows.net
```

### 4.3 Create a Test Index

```bash
# Get admin key
ADMIN_KEY=$(az search admin-key show \
  --resource-group "rg-private-network-test" \
  --service-name $AI_SEARCH_NAME \
  --query "primaryKey" -o tsv)

# Create a simple index
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
```

---

## Step 5: Test Microsoft Fabric Integration

### 5.1 Prerequisites for Fabric Testing

> **Note:** Contact the Fabric team (Piotr Karpala) to obtain a test Fabric resource.

To test Fabric integration, you need:
1. An existing Microsoft Fabric capacity
2. The Fabric capacity must support private link connectivity
3. The Fabric workspace resource ID

### 5.2 Deploy with Fabric

```bash
# Deploy with Fabric private endpoint
az deployment group create \
  --resource-group "rg-private-network-test" \
  --template-file main.bicep \
  --parameters location="norwayeast" \
  --parameters fabricWorkspaceResourceId="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Fabric/capacities/<capacity-name>"
```

### 5.3 Verify Fabric Private Endpoint

```bash
# Check Fabric private endpoint
az network private-endpoint show \
  --resource-group "rg-private-network-test" \
  --name "*-fabric-private-endpoint" \
  --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState"
```

### 5.4 Test Fabric Connectivity

From within the VNet:

```bash
# Test DNS resolution for Fabric
nslookup <fabric-workspace>.analysis.windows.net

# The IP should be a private IP (10.x.x.x or 192.168.x.x)
```

---

## Step 6: Test MCP Remote Servers on VNet

### 6.1 Overview

MCP (Model Context Protocol) Remote Servers can be deployed on the VNet to provide additional tools to AI agents while maintaining network isolation.

> **Note:** The agent subnet is delegated to `Microsoft.App/environments` (Azure Container Apps), not `Microsoft.ContainerInstance/containerGroups`. You must use Azure Container Apps to deploy containers in this subnet.

### 6.2 Deploy MCP Everything Server

Deploy an MCP server container in the VNet using Azure Container Apps:

```bash
# Step 1: Create a Container Apps Environment connected to the VNet
az containerapp env create \
  --resource-group "rg-private-network-test" \
  --name "mcp-env" \
  --location "norwayeast" \
  --infrastructure-subnet-resource-id "/subscriptions/<sub-id>/resourceGroups/rg-private-network-test/providers/Microsoft.Network/virtualNetworks/<vnet-name>/subnets/agent-subnet" \
  --internal-only true

# Step 2: Deploy the MCP server as a Container App
az containerapp create \
  --resource-group "rg-private-network-test" \
  --name "mcp-everything-server" \
  --environment "mcp-env" \
  --image "mcpeverything/server:latest" \
  --target-port 8080 \
  --ingress internal \
  --cpu 1.0 \
  --memory 2.0Gi

# Step 3: Get the internal FQDN of the MCP server
az containerapp show \
  --resource-group "rg-private-network-test" \
  --name "mcp-everything-server" \
  --query "properties.configuration.ingress.fqdn" -o tsv
```

### 6.3 Verify MCP Server is Only Accessible from VNet

**From within the VNet (should work):**
```bash
# Use the FQDN from the previous step
curl http://<mcp-server-fqdn>/health
```

**From outside the VNet (should fail):**
```bash
# This should timeout or fail - confirming network isolation
curl --connect-timeout 5 http://<mcp-server-fqdn>/health
```

### 6.4 Configure Agent to Use MCP Server

Once the MCP server is running on the VNet, configure your AI Foundry agent to use it as a tool provider:

1. Navigate to Azure AI Foundry portal
2. Access your project (created by the deployment)
3. Create or edit an agent
4. Add MCP server endpoint as a tool source: `http://<mcp-server-fqdn>:8080`

---

## Cleanup

### Delete All Resources

```bash
# Delete the resource group and all resources
az group delete --name "rg-private-network-test" --yes --no-wait
```

### Partial Cleanup (Keep VNet)

If you want to keep the VNet for future testing:

1. First delete the project capability host:
   ```bash
   ./deleteCapHost.sh
   ```

2. Wait ~20 minutes for resources to unlink

3. Purge the AI Services account:
   ```bash
   az cognitiveservices account purge \
     --resource-group "rg-private-network-test" \
     --name "<account-name>" \
     --location "norwayeast"
   ```

---

## Troubleshooting

### Common Issues

#### 1. "Subnet already in use" Error

**Cause:** Previous capability host wasn't properly deleted.

**Solution:**
1. Delete and purge the AI Services account
2. Wait 20 minutes for subnet to be released
3. Redeploy

#### 2. DNS Resolution Fails

**Cause:** Private DNS zones not linked to VNet.

**Solution:**
```bash
# Check DNS zone links
az network private-dns link vnet list \
  --resource-group "rg-private-network-test" \
  --zone-name "privatelink.search.windows.net"
```

#### 3. Cannot Access Resources from Jump Box

**Cause:** Jump box in wrong subnet or NSG blocking traffic.

**Solution:**
- Ensure jump box is in the PE subnet or has route to it
- Check NSG rules allow outbound HTTPS (443)

#### 4. Fabric Private Endpoint Not Created

**Cause:** `fabricWorkspaceResourceId` parameter was empty or invalid.

**Solution:**
- Verify the Fabric resource ID format
- Ensure Fabric capacity supports private link

### Useful Diagnostic Commands

```bash
# Check private endpoint connection status
az network private-endpoint show \
  --resource-group "rg-private-network-test" \
  --name "<pe-name>" \
  --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState"

# Test DNS resolution
nslookup <resource>.privatelink.<service>.azure.com

# List all private DNS records
az network private-dns record-set list \
  --resource-group "rg-private-network-test" \
  --zone-name "privatelink.search.windows.net"
```

---

## Next Steps

1. **Production Deployment**: Use existing enterprise VNet with VPN/ExpressRoute
2. **Security Hardening**: Add NSG rules, Azure Firewall, and Azure Policy
3. **Monitoring**: Enable diagnostic logs and Azure Monitor
4. **CI/CD Integration**: Automate deployments with Azure DevOps or GitHub Actions

---

## Contact

For questions about:
- **Fabric integration**: Contact Matt Luker or Anand Raman
- **MCP Remote Servers**: Check MCP documentation (for networking - contact Piotr Karpala)
- **Azure AI Foundry**: See [Azure AI Foundry documentation](https://learn.microsoft.com/azure/ai-foundry/)
