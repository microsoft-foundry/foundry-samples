# Hybrid Private Resources Agent Setup

This template deploys an Azure AI Foundry account with **public API access** while keeping backend resources (AI Search, Cosmos DB, Storage) on **private endpoints**. This hybrid architecture enables portal-based agent testing with tools that access private resources.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              INTERNET                                │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      AI Services Account     │
                    │   (publicNetworkAccess:      │
                    │        ENABLED)              │  ◄── Portal works!
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │   Data Proxy / Agent   │  │
                    │  │      ToolServer        │  │
                    │  └───────────┬────────────┘  │
                    └──────────────┼──────────────┘
                                   │ networkInjections
                    ┌──────────────▼──────────────┐
                    │     Private VNet             │
                    │                              │
                    │  ┌─────────┐ ┌─────────┐    │
                    │  │AI Search│ │Cosmos DB│    │  ◄── Private endpoints
                    │  └─────────┘ └─────────┘    │      (no public access)
                    │                              │
                    │  ┌─────────┐ ┌─────────┐    │
                    │  │ Storage │ │   MCP   │    │
                    │  └─────────┘ │ Servers │    │
                    │              └─────────┘    │
                    └─────────────────────────────┘
```

## Key Features

| Feature | This Template (19) | Fully Private (15) |
|---------|-------------------|-------------------|
| AI Services public access | ✅ Enabled | ❌ Disabled |
| Portal access | ✅ Works | ❌ Not supported |
| Backend resources | 🔒 Private | 🔒 Private |
| Data Proxy | ✅ Configured | ✅ Configured |
| Jump box required | Optional | Required |

## When to Use This Template

Use this template when you want:
- **Portal-based development** - Create and test agents in the Azure AI Foundry portal
- **Private data resources** - Keep AI Search, Cosmos DB, and Storage behind private endpoints
- **MCP server integration** - Deploy MCP servers on the VNet that agents can access via Data Proxy
- **Simpler testing** - No jump box required for portal access

## When NOT to Use This Template

Use [template 15](../15-private-network-standard-agent-setup/) instead when you need:
- **Full network isolation** - AI Services API must not be publicly accessible
- **Zero-trust architecture** - All access must go through VPN/ExpressRoute
- **Compliance requirements** - Regulations require fully private endpoints

## Deployment

### Prerequisites

1. Azure CLI installed and authenticated
2. Owner or Contributor role on the subscription
3. Sufficient quota for model deployment (gpt-4o-mini)

### Deploy

```bash
# Create resource group
az group create --name "rg-hybrid-agent-test" --location "westus2"

# Deploy the template
az deployment group create \
  --resource-group "rg-hybrid-agent-test" \
  --template-file main.bicep \
  --parameters location="westus2"
```

### Verify Deployment

```bash
# Check deployment status
az deployment group show \
  --resource-group "rg-hybrid-agent-test" \
  --name "main" \
  --query "properties.provisioningState"

# List private endpoints (should see AI Search, Storage, Cosmos DB)
az network private-endpoint list \
  --resource-group "rg-hybrid-agent-test" \
  --output table
```

## Testing Agents with Private Resources

### Option 1: Portal Testing (Recommended)

1. Navigate to [Azure AI Foundry portal](https://ai.azure.com)
2. Select your project
3. Create an agent with AI Search tool
4. Test that the agent can query the private AI Search index

### Option 2: SDK Testing

See [TESTING-GUIDE.md](TESTING-GUIDE.md) for detailed SDK testing instructions.

## MCP Server Deployment

To deploy MCP servers on the private VNet:

```bash
# Create Container Apps environment on mcp-subnet
az containerapp env create \
  --resource-group "rg-hybrid-agent-test" \
  --name "mcp-env" \
  --location "westus2" \
  --infrastructure-subnet-resource-id "<mcp-subnet-resource-id>" \
  --internal-only true

# Deploy MCP server
az containerapp create \
  --resource-group "rg-hybrid-agent-test" \
  --name "my-mcp-server" \
  --environment "mcp-env" \
  --image "<your-mcp-image>" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1
```

Then configure private DNS zone for Container Apps (see TESTING-GUIDE.md Step 6.3).

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `location` | Azure region | `eastus2` |
| `aiServices` | Base name for AI Services | `aiservices` |
| `modelName` | Model to deploy | `gpt-4o-mini` |
| `modelCapacity` | TPM capacity | `30` |
| `vnetName` | VNet name | `agent-vnet-test` |
| `agentSubnetName` | Subnet for AI Foundry (reserved) | `agent-subnet` |
| `peSubnetName` | Subnet for private endpoints | `pe-subnet` |
| `mcpSubnetName` | Subnet for MCP servers | `mcp-subnet` |

## Cleanup

```bash
# Delete all resources
az group delete --name "rg-hybrid-agent-test" --yes --no-wait
```

## Related Templates

- [15-private-network-standard-agent-setup](../15-private-network-standard-agent-setup/) - Fully private setup (no public access)
- [40-basic-agent-setup](../40-basic-agent-setup/) - Basic agent setup without private networking
- [41-standard-agent-setup](../41-standard-agent-setup/) - Standard agent setup without private networking
