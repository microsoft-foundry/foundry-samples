---
description: This set of templates demonstrates how to set up Foundry Agent Service with virtual network isolation, private network links, and tools behind VNet.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent-tools
languages:
- bicep
- json
---

# Microsoft Foundry: Standard Agent Setup with E2E Network Isolation with Tools behind VNET

> **NEW**
> For support on deploying the right network isolation template, check out the [GitHub Copilot for Azure skill for private networking](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/resource/private-network/private-network.md) set-up!

> **IMPORTANT**
> When testing all the Agent tools behind a VNET, please use the [TESTING-GUIDE.md](tests/TESTING-GUIDE.md) file in this repository to ensure your tools are set-up correctly. Currently supported Agent tools behind a VNET include: private MCP, OpenAPI, A2A, Azure Functions, AI Search, Fabric Data Agent. More tools behind a VNET support is coming soon! 

---
## Overview
This infrastructure-as-code (IaC) solution deploys a network-secured agent environment with private networking, role-based access control (RBAC), and support for tools behind the VNet (MCP servers, OpenAPI tools, Azure Functions, A2A).

Standard setup supports private network isolation through utilizing **Bring Your Own Virtual Network (BYO VNet)** approach, also known as **custom VNet support with subnet delegation.**

This implementation gives you full control over the inbound and outbound communication paths for your agent. You can restrict access to only the resources explicitly required by your agent, such as storage accounts, databases, or APIs, while blocking all other traffic by default. This approach ensures that your agent operates within a tightly scoped network boundary, reducing the risk of data leakage or unauthorized access. By default, this setup simplifies security configuration while enforcing strong isolation guarantees, ensuring that each agent deployment remains secure, compliant, and aligned with enterprise networking policies.

By default, the Foundry resource itself also has **public network access disabled**, but this can be switched to public access if needed (see [Switching Between Private and Public Access](#switching-between-private-and-public-access)).

---

## When to Use This Template

Use this template when you need:
- **Full end-to-end network isolation** — All resources behind private endpoints with no public internet access
- **BYO VNet control** — You manage your own virtual network, subnets, and network security groups
- **Standard agent setup with BYO resources** — Customer-managed Storage, Cosmos DB, and AI Search for data residency and compliance
- **Tools behind VNet** — MCP servers, OpenAPI tools, Azure Functions, or A2A agents deployed on the private VNet
- **System Assigned Managed Identity** — Simplified identity management with platform-managed credentials

### Template Decision Guide

Use the table below to choose the right infrastructure template for your scenario:

| Template | Agent Type | Networking | Identity | Key Use Case |
|----------|-----------|------------|----------|-------------|
| [**15**](../15-private-network-standard-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | E2E network isolation with full agent capabilities |
| [**19** (this template)](../19-private-network-agent-tools/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** tools behind VNet (MCP, OpenAPI, Functions, A2A) |
| [**17**](../17-private-network-standard-user-assigned-identity-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | **User Assigned MI** | Same as 15 but with user-managed identity |
| [**16**](../16-private-network-standard-agent-apim-setup-preview/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** private APIM integration (preview) |
| [**18**](../18-managed-virtual-network-preview/) | Standard (BYO resources) | **Managed VNet** (Microsoft-managed) | System Assigned MI | Network isolation without managing your own VNet (preview) |
| [**15a**](../15a-private-network-evaluation-only-setup/) | Evaluation only | BYO VNet + Private Endpoints | System Assigned MI | Minimal setup for evaluation — no Cosmos DB, AI Search, or capability host |
| [**11**](../11-private-network-basic-vnet/) | **Basic** (platform-managed) | BYO VNet injection | System Assigned MI | Basic agents with VNet isolation — no BYO resources needed |
| [**41**](../41-standard-agent-setup/) | Standard (BYO resources) | **Public** (no VNet) | System Assigned MI | Standard agents without network isolation |
| [**40**](../40-basic-agent-setup/) | **Basic** (platform-managed) | **Public** (no VNet) | System Assigned MI | Simplest setup — no BYO resources, no private networking |

### Key Features

| Feature | This Template (19) — Private (default) | This Template (19) — Public | Fully Private (15) |
|---------|----------------------------------------|-----------------------------|-----------------------|
| AI Services public access | ❌ Disabled | ✅ Enabled | ❌ Disabled |
| Portal access | Via VPN/ExpressRoute/Bastion | ✅ Works directly | Via VPN/ExpressRoute/Bastion |
| Backend resources | 🔒 Private | 🔒 Private | 🔒 Private |
| Data Proxy | ✅ Configured | ✅ Configured | ✅ Configured |
| Tools behind VNet (MCP, OpenAPI, Functions, A2A) | ✅ Supported | ✅ Supported | ❌ Not supported |
| Secure connection required | ✅ Yes | ❌ No | ✅ Yes |

---

## Deploy to Azure

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F19-private-network-agent-tools%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F19-private-network-agent-tools%2FcreateUiDefinition.json)

> The "Deploy to Azure" button uses [`createUiDefinition.json`](./createUiDefinition.json) to render a guided wizard in the Azure Portal: real VNet/subnet pickers, resource pickers for AI Search / Cosmos / Storage, and per-field validation \u2014 instead of the default flat list of 27 text boxes.


---

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
  - **Foundry Account Owner**: Needed to create the Microsoft Foundry account and project.
  - **Owner or Role Based Access Administrator**: Needed to assign RBAC on the Azure resources used by this template.
  - **Foundry User**: Needed to create and use agents, projects, or evaluation workloads after deployment.

1. **Register Resource Providers**

   Make sure you have an active Azure subscription that allows registering resource providers. For example, subnet delegation requires the Microsoft.App provider to be registered in your subscription. If it's not already registered, run the commands below:

   ```bash
   az provider register --namespace 'Microsoft.KeyVault'
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Storage'
   az provider register --namespace 'Microsoft.Search'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.App'
   az provider register --namespace 'Microsoft.ContainerService'
   ```

1. Network administrator permissions (if operating in a restricted or enterprise environment)

1. Sufficient quota for all resources required by this template in the target Azure region, including model deployment quota.
    * If no parameters are passed in, this template creates an Microsoft Foundry resource, Foundry project, Azure Cosmos DB for NoSQL, Azure AI Search, and Azure Storage account
1. Azure CLI installed and configured on your local workstation or deployment pipeline server

> **💡 Recommended**: Run the [preflight check](../deployment-tools/preflight/README.md) before deploying to catch common misconfigurations (provider registration, subnet conflicts, soft-deleted accounts) before they surface as cryptic ARM errors mid-deploy.

---

## Pre-Deployment Steps

### Networking Requirements
1. Review network requirements and plan Virtual Network address space (e.g., 192.168.0.0/16 or an alternative non-overlapping address space)

2. Three subnets are needed:
    - **Agent Subnet** (e.g., 192.168.0.0/24): Hosts Agent client for Agent workloads, delegated to Microsoft.App/environments. The recommended size should be /24 for this delegated subnet.
    - **Private endpoint Subnet** (e.g., 192.168.1.0/24): Hosts private endpoints
    - **MCP Subnet** (e.g., 192.168.2.0/24): Hosts MCP servers, OpenAPI tools, Azure Functions, and A2A agents on the VNet
    - Ensure that the address spaces for the used VNET does not overlap with any existing networks in your Azure environment or reserved IP ranges like the following: 169.254.0.0/16,172.30.0.0/16,172.31.0.0/16,192.0.2.0/24,0.0.0.0/8,127.0.0.0/8,100.100.0.0/17,100.100.192.0/19,100.100.224.0/19,100.64.0.0/11.
    This includes all address space(s) you have in your VNET if you have more than one, and peered VNETs.

  > **Notes:**
  - If you do not provide an existing virtual network, the template will create a new virtual network with the default address spaces and subnets described above. If you use an existing virtual network, make sure it already contains three subnets (Agent, Private Endpoint, and MCP) before deploying the template.
  - You must ensure the Foundry account was successfully created so that underlying caphost has also succeeded. Then proceed to deploying the project caphost bicep.
  - You must ensure the agent subnet is exclusively delegated to __Microsoft.App/environments__ and cannot be used by any other Azure resources.

### Limitations / Known Issues

1. The delegated agent subnet must be exclusively used by a single Foundry account. It cannot be shared across accounts.
2. The Foundry resource and the virtual network must be in the same Azure region. BYO resources (Storage, Cosmos DB, AI Search) may be in different regions.
3. For the virtual network IP range, you may use any Private Class A, B or C IP range. Private Class A IP address ranges (10.x.x.x) are only supported in the following regions: **Australia East, Brazil South, Canada East, East US, East US 2, France Central, Germany West Central, Italy North, Japan East, South Africa North, South Central US, South India, Spain Central, Sweden Central, UAE North, UK South, West US, West US 3.** Use Class B (172.16.x.x) or C (192.168.x.x) ranges for other regions. You may not use any other IP range that overlaps to the list above or uses public IP ranges. 
4. There is no upgrade path from BYO VNet (this template) to Managed Virtual Network (template 18). A Foundry resource redeployment is required.
5. All projects within the same Foundry account share model deployments. Per-project model isolation is not supported.
6. Cosmos DB is deployed as single-region. Multi-region replication must be configured manually post-deployment.

### Switching Between Private and Public Access

The Foundry resource has **public network access disabled by default**. You can switch between the two modes by modifying the Bicep template.

#### To enable public access

In [modules-network-secured/ai-account-identity.bicep](modules-network-secured/ai-account-identity.bicep), change:

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

This makes the Foundry resource accessible from the internet (e.g., for portal-based development without VPN).

#### To disable public access (default)

Revert the changes above, setting `publicNetworkAccess: 'Disabled'` and `defaultAction: 'Deny'`.

### Account Deletion Prerequisites and Cleanup Guidance

Before deleting an **Account** resource, it is essential to first delete the associated **Account Capability Host**. Failure to do so may result in residual dependencies—such as subnets and other provisioned resources (e.g., ACA applications)—remaining linked to the capability host. This can lead to errors such as **"Subnet already in use"** when attempting to reuse the same subnet in a different account deployment.

**Cleanup Options**

**1. Full Account Removal**: To completely remove an account, you must delete and purge the account. Simply deleting the account is not sufficient, you must purge so that deletion of the associated capability host is triggered. The service will automatically handle the removal of the capability host and any linked resources in the background. To purge the account, use the following [link](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource). Please allow approximately max of 20 minutes for all resources to be fully unlinked from the account. The account capability host can remain in **Deleting** for approximately 20–30 minutes; wait until it is gone before reusing the Agent Subnet.

**2. Retain Account, Remove Capability Host**: If you intend to retain the account but remove the capability host, execute the script `deleteCapHost.sh` located in this folder. After deletion, allow approximately max of 20 minutes for all resources to be fully unlinked from the account. To recreate the capability host for the account, use the script `createCapHost.sh` located in the same folder.

> **Important**: Before deleting the account capability host, ensure that the **project capability host** is deleted.

### Template Customization

Note: If not provided, the following resources will be created automatically for you:
- VNet and three subnets (Agent, PE, MCP)
- Azure Cosmos DB for NoSQL
- Azure AI Search
- Azure Storage
- Azure Container Registry (Premium SKU) with private endpoint *(when `enableContainerRegistry=true`)*

#### Parameters

> **⚠️ Important: Cosmos DB Connection Requirements**
>
> If you are creating the Cosmos DB connection manually (e.g., via REST API or ARM), ensure the following:
> - The `authType` **must** be set to `AAD`. This is the only supported authentication type for the Cosmos DB connection used by the Agent Service.
> - The `metadata` section **must** include the `ResourceId` property, set to the full Azure Resource ID of your Cosmos DB account. The Agent Service relies on this property to correctly identify and connect to your Cosmos DB resource. Omitting `ResourceId` from the metadata will cause the connection to fail.
>
> Example connection properties:
> ```json
> {
>   "category": "CosmosDB",
>   "authType": "AAD",
>   "metadata": {
>     "ApiType": "Azure",
>     "ResourceId": "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName}",
>     "location": "{region}"
>   }
> }
> ```

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `location` | Azure region for deployment | `eastus2` | Yes |
| `aiServices` | Base name for the AI Services resource (2-40 lowercase chars) | `contoso` | No |
| `firstProjectName` | Name for the Foundry project | `project` | No |
| `modelName` | Model to deploy | `gpt-4o-mini` | No |
| `modelFormat` | Model provider | `OpenAI` | No |
| `modelVersion` | Model version | `2024-07-18` | No |
| `modelSkuName` | Model deployment SKU | `GlobalStandard` | No |
| `modelCapacity` | Tokens per minute (TPM) capacity | `30` | No |
| `vnetName` | Virtual Network name (ignored when `existingVnetResourceId` is set) | `agent-vnet` | No |
| `agentSubnetName` | Agent subnet name (ignored when `existingAgentSubnetResourceId` is set) | `agent-subnet` | No |
| `agentSubnetPrefix` | Address prefix for agent subnet | `''` (auto) | No |
| `peSubnetName` | Private endpoint subnet name (ignored when `existingPeSubnetResourceId` is set) | `pe-subnet` | No |
| `peSubnetPrefix` | Address prefix for PE subnet | `''` (auto) | No |
| `mcpSubnetName` | MCP subnet name (ignored when `existingMcpSubnetResourceId` is set) | `mcp-subnet` | No |
| `mcpSubnetPrefix` | Address prefix for MCP subnet | `''` (auto) | No |
| `existingVnetResourceId` | Full ARM Resource ID of an existing VNet | `''` (creates new) | No |
| `existingAgentSubnetResourceId` | Full ARM ID of an existing agent subnet to reuse as-is | `''` (creates) | No |
| `existingPeSubnetResourceId` | Full ARM ID of an existing PE subnet to reuse as-is | `''` (creates) | No |
| `existingMcpSubnetResourceId` | Full ARM ID of an existing MCP subnet to reuse as-is | `''` (creates) | No |
| `vnetAddressPrefix` | Address space for new VNet | `''` | No |
| `existingAiSearchResourceId` | ARM Resource ID of existing AI Search | `''` (creates new) | No |
| `existingAzureStorageAccountResourceId` | ARM Resource ID of existing Storage account | `''` (creates new) | No |
| `existingAzureCosmosDBAccountResourceId` | ARM Resource ID of existing Cosmos DB | `''` (creates new) | No |
| `existingFabricWorkspaceResourceId` | ARM Resource ID of existing Fabric workspace | `''` | No |
| `existingDnsZones` | Map of `'<zoneFqdn>': { subscriptionId, resourceGroup }` — see [Use existing Private DNS zones](#5-use-existing-private-dns-zones-cross-rg--cross-subscription) | All `{ subscriptionId: '', resourceGroup: '' }` (creates new) | No |
| `enableContainerRegistry` | When `true`, creates an Azure Container Registry (Premium SKU) with a private endpoint in the PE subnet, a `privatelink.azurecr.io` DNS zone, and an AcrPull role assignment for the project managed identity. | `true` | No |
| `developerIpCidr` | Developer IP CIDR to allowlist for ACR push access (e.g., `203.0.113.0/26`). When set, enables public network access with a deny-all default + an IP allowlist rule so developers can push images. When empty, public access remains fully disabled. | `''` | No |

> **Naming change (May 2026):** `aiSearchResourceId`, `azureStorageAccountResourceId`, `azureCosmosDBAccountResourceId`, and `fabricWorkspaceResourceId` were renamed to `existingAiSearchResourceId`, `existingAzureStorageAccountResourceId`, `existingAzureCosmosDBAccountResourceId`, and `existingFabricWorkspaceResourceId` for consistency with the `existing*ResourceId` pattern used by VNet and subnet params. Update existing parameter files accordingly.

#### BYO Resource Details

1. **Use Existing Virtual Network and Subnets**

To use an existing VNet and subnets, set the `existingVnetResourceId` parameter to the full ARM ID of the target VNet. Provide the names (or, recommended, the full ARM IDs) of the three subnets you want to use.

There are two levels of "existing" support:

* **Existing VNet, let the template manage subnets** — set only `existingVnetResourceId` and the per-subnet `*Name` / `*Prefix` params. The template will look up the VNet and create/update the three subnets inside it.
* **Existing VNet AND existing subnets (recommended for shared / production VNets)** — also set `existingAgentSubnetResourceId`, `existingPeSubnetResourceId`, and/or `existingMcpSubnetResourceId` to the full ARM IDs of subnets you already have. When set, those subnets are referenced as-is and **not created or modified** — preserving their existing NSGs, route tables, and delegations.

Example:

```bicep
param existingVnetResourceId        = '/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>'
param existingAgentSubnetResourceId = '/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/agent-subnet'
param existingPeSubnetResourceId    = '/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/pe-subnet'
param existingMcpSubnetResourceId   = '/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/mcp-subnet'
param existingDnsZones = {
  'privatelink.services.ai.azure.com': { subscriptionId: '', resourceGroup: 'shared-dns-rg' }   // existing zone, same sub, different RG
  'privatelink.openai.azure.com':      { subscriptionId: '', resourceGroup: '' }                // create a new zone in this deployment’s RG
  // ... etc
}
```

💡 **When to use which**:
* If the VNet is yours and the subnets are empty/unused → just set `existingVnetResourceId`.
* If the VNet is shared with other workloads → always set the `existing*SubnetResourceId` params too. Otherwise, the template will issue subnet PUTs that can fail with `AnotherOperationInProgress` or, worse, succeed and overwrite settings managed by another team.

💡 If subnets information is provided then make sure it exist within the specified VNet to avoid deployment errors. If subnet information is not provided, the template will create subnets with the default address space.


2. **Use an existing Azure Cosmos DB for NoSQL**

To use an existing Cosmos DB for NoSQL resource, set `existingAzureCosmosDBAccountResourceId` to the full Azure Resource ID of the target Cosmos DB.
- `param existingAzureCosmosDBAccountResourceId = '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName}'`


3. **Use an existing Azure AI Search resource**

To use an existing Azure AI Search resource, set `existingAiSearchResourceId` to the full ARM ID of the target search service.
 - `param existingAiSearchResourceId = '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Search/searchServices/{searchServiceName}'`

> **AI Search → AI Services connectivity**: This template configures AI Services with `networkAcls.bypass: AzureServices`, which allows Azure AI Search to reach AI Services through the trusted-services bypass. This works for most scenarios. If your security policy requires removing the bypass (setting it to `None`), deploy [Shared Private Links](../deployment-tools/networking/README.md) from AI Search to AI Services instead — this creates a private endpoint from AI Search's managed infrastructure directly into AI Services via Private Link.


4. **Use an existing Azure Storage account**

To use an existing Azure Storage account, set `existingAzureStorageAccountResourceId` to the full ARM ID of the target storage account.
- `param existingAzureStorageAccountResourceId = '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}'`

5. **Use existing Private DNS zones (cross-RG / cross-subscription)**

The `existingDnsZones` parameter controls, **per zone**, whether the template creates a new private DNS zone in this deployment’s resource group or references an existing one (optionally in another resource group and/or subscription).

Each map value is an object with two optional properties:

| Property | Meaning |
|---|---|
| `resourceGroup` | RG holding the existing zone. **Empty `''` → create a new zone in this deployment’s RG.** Non-empty → reference the existing zone in that RG. |
| `subscriptionId` | Subscription holding the existing zone. Empty `''` defaults to the current subscription. Only used when `resourceGroup` is non-empty. |

Three usage modes:

```bicep
param existingDnsZones = {
  // (a) Create a new zone in this deployment's RG (default behavior)
  'privatelink.blob.core.windows.net':       { subscriptionId: '', resourceGroup: '' }

  // (b) Reference an existing zone in another RG, SAME subscription
  'privatelink.openai.azure.com':            { subscriptionId: '', resourceGroup: 'shared-dns-rg' }

  // (c) Reference an existing zone in another RG and ANOTHER subscription
  'privatelink.search.windows.net':          { subscriptionId: '11111111-2222-3333-4444-555555555555', resourceGroup: 'hub-dns-rg' }
}
```

> ⚠️ **You must pre-link the VNet to any referenced zone.** When the template references an existing zone (modes b and c), it intentionally **does not create the `virtualNetworkLinks` resource** — the deployment identity may not have write rights in the zone’s RG/subscription. Ensure the zone is already linked to the VNet hosting the private endpoints, otherwise name resolution will fail even though the deployment succeeds.

> ⚠️ **Cross-subscription RBAC.** The deployment principal needs `Private DNS Zone Contributor` (or at least `reader` + permission to write zone groups) on each referenced zone’s scope. For mode (c), grant this in the target subscription.

> 💡 **Migrating from the old string format.** Earlier versions accepted `'<zone>': '<rgName>'`. Replace each value with `{ subscriptionId: '', resourceGroup: '<rgName>' }` (or `{ subscriptionId: '', resourceGroup: '' }` to create new).

---

## Deploy the bicep template

Choose your deployment method: Use the "Deploy to Azure" button from the provided README for a guided experience in Azure Portal

**Option 1: Automatic deployment**
Click the deploy to Azure button above to open the Azure portal and deploy the template directly.
- Fill in the parameters as needed, including the existing VNet and subnets if applicable.


**Option 2: Manually deploy the bicep template**
- **Create a New (or Use Existing) Resource Group**

   ```bash
   az group create --name <new-rg-name> --location <your-rg-region>
   ```
- Deploy the main.bicep file
  - Edit the main.bicepparams file to use an existing Virtual Network & subnets, Azure Cosmos DB, Azure Storage, and Azure AI Search.

   ```bash
      az deployment group create --resource-group <your-resource-group> --template-file main.bicep --parameters main.bicepparam
   ```

> **Note:** To access a private Foundry resource securely, use one of the following:
> - A VM or jump box on the virtual network, optionally accessed through Azure Bastion
> - Azure VPN Gateway
> - Azure ExpressRoute

If public network access is enabled, you can also access the Foundry resource directly from the internet for portal-based development.

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

### Cleanup

To delete all resources created by this template:

```bash
az group delete --name <your-resource-group> --yes --no-wait
```

> **Important**: If you need to reuse the same subnet, follow the [Account Deletion Prerequisites and Cleanup Guidance](#account-deletion-prerequisites-and-cleanup-guidance) to properly purge the account and wait for the capability host to fully unlink (~20 minutes).

> **💡 Tip**: For VNet-injection deployments, use the [cleanup tool](../deployment-tools/cleanup/README.md) it handles the required deletion order (project caphost → account caphost → purge → SAL wait) automatically.

---

## Network Secured Agent Project Architecture Deep Dive

```
┌─────────────────────────────────────────────────────────────────────┐
│  Secure Access (VPN Gateway / ExpressRoute / Azure Bastion)         │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Microsoft Foundry          │
                    │   (publicNetworkAccess:      │
                    │        DISABLED)             │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │   Foundry Project       │  │
                    │  │   (Agent Workspace)     │  │
                    │  └───────────┬────────────┘  │
                    └──────────────┼──────────────┘
                                   │ Subnet Delegation
                    ┌──────────────▼──────────────┐
                    │   BYO Virtual Network        │
                    │   (192.168.0.0/16)           │
                    │                              │
                    │  ┌──────────────────────┐    │
                    │  │ Agent Subnet          │   │
                    │  │ (192.168.0.0/24)      │   │  ◄── Delegated to
                    │  │ Microsoft.App/envs    │   │      Microsoft.App/environments
                    │  └──────────────────────┘    │
                    │                              │
                    │  ┌──────────────────────┐    │
                    │  │ PE Subnet             │   │
                    │  │ (192.168.1.0/24)      │   │
                    │  │                       │   │
                    │  │ ┌────────┐ ┌────────┐ │   │
                    │  │ │Storage │ │Cosmos  │ │   │  ◄── Private endpoints
                    │  │ └────────┘ └────────┘ │   │      (no public access)
                    │  │ ┌────────┐ ┌────────┐ │   │
                    │  │ │Search  │ │Foundry │ │   │
                    │  │ └────────┘ └────────┘ │   │
                    │  └──────────────────────┘    │
                    │                              │
                    │  ┌──────────────────────┐    │
                    │  │ MCP Subnet            │   │
                    │  │ (192.168.2.0/24)      │   │
                    │  │                       │   │
                    │  │ ┌────────┐ ┌────────┐ │   │
                    │  │ │  MCP   │ │OpenAPI │ │   │  ◄── Tools behind VNet
                    │  │ │Servers │ │ Tools  │ │   │
                    │  │ └────────┘ └────────┘ │   │
                    │  │ ┌────────┐ ┌────────┐ │   │
                    │  │ │Azure   │ │  A2A   │ │   │
                    │  │ │Funcs   │ │Agents  │ │   │
                    │  │ └────────┘ └────────┘ │   │
                    │  └──────────────────────┘    │
                    └──────────────────────────────┘
```

> **Tip:** For detailed layer-by-layer deployment diagrams, see the `diagrams/` folder.

### Core Components

**Microsoft Foundry** resource
- Central orchestration point
- Manages service connections
- Set networking and policy configurations

**Foundry** project
- Defines the workspace configuration
- Service integration
- Agents are created within a specific project, and each project acts as an isolated workspace. This means:
  - All agents in the same project share access to the same file storage, thread storage (conversation history), and search indexes.
  - Data is isolated between projects. Agents in one project cannot access resources from another. Projects are currently the unit of sharing and isolation in Foundry. See the what is AI foundry article for more information on Foundry projects.

**Bring Your Own (BYO) Azure Resources**: ensures all sensitive data remains under customer control. All agents created using our service are stateful, meaning they retain information across interactions. With this setup, agent states are automatically stored in customer-managed, single-tenant resources. The required Bring Your Own Resources include:
- BYO File Storage: All files uploaded by developers (during agent configuration) or end-users (during interactions) are stored directly in the customer's Azure Storage account.
- BYO Search: All vector stores created by the agent leverage the customer's Azure AI Search resource.
- BYO Thread Storage: All customer messages and conversation history will be stored in the customer's own Azure Cosmos DB account.

By bundling these BYO features (file storage, search, and thread storage), the standard setup guarantees that your deployment is secure by default. All data processed by Microsoft Foundry Agent Service is automatically stored at rest in your own Azure resources, helping you meet internal policies, compliance requirements, and enterprise security standards.

### Azure Resources Created

Microsoft Foundry (Cognitive Services)
- Type: Microsoft.CognitiveServices/accounts
- API version: 2025-04-01-preview
- Kind: AIServices
- SKU: S0
- Identity: System-assigned
- Features:
  - Custom subdomain name
  - Disabled public network access
  - Network ACLs with Azure Services bypass

AI Model Deployment
- Type: Microsoft.CognitiveServices/accounts/deployments
- API version: 2025-04-01-preview
- SKU: Based on modelSkuName parameter, capacity set by modelCapacity
- Model properties:
  - Name: From modelName parameter
  - Format: From modelFormat parameter
  - Version: From modelVersion parameter

Azure AI Search
- Type: Microsoft.Search/searchServices
- API version: 2024-06-01-preview
- SKU: standard
- Partition Count: 1
- Replica Count: 1
- Hosting Mode: default
- Semantic Search: disabled
- Features:
  -  Disabled public network access
  -  AAD auth with HTTP 401 challenge
  -  System-assigned managed identity

Storage Account
- Type: Microsoft.Storage/storageAccounts
- API version: 2023-05-0
- Kind: StorageV2
- SKU: ZRS or GRS (region dependent; use Standard_GRS if ZRS not available)
- Features:
  - Blob service, Queue service (if Azure Function Tool supported)
  - Minimum TLS Version: 1.2
  - Block public blob access
  - Disabled public network access
  - Force Azure AD authentication (SharedKey access disabled)

Cosmos DB Account
- Type: Microsoft.DocumentDB/databaseAccounts
- API version: 2024-11-15
- Kind: GlobalDocumentDB (SQL API)
- Consistency Level: Session
- Database Account Offer Type: Standard
- Features:
  - Disabled public network access
  - Disabled local auth
  - Single region deployment

Azure Monitor (Application Insights & Log Analytics)
- Log Analytics Workspace: Microsoft.OperationalInsights/workspaces
  - SKU: PerGB2018
  - Retention: 30 days
- Application Insights: Microsoft.Insights/components
  - Kind: web
  - Linked to Log Analytics workspace
  - Public ingestion disabled (reached privately via AMPLS)
- Azure Monitor Private Link Scope (AMPLS): microsoft.insights/privateLinkScopes
  - Access mode: PrivateOnly ingestion, Open query
  - Scoped resources: Application Insights + Log Analytics
  - Enables hosted agents to export telemetry via private network

### Network Security Design
This implementation utilizes a BYO VNet (Bring Your Own Virtual Network) approach, also known as custom VNet support with subnet delegation. Within your existing virtual network, delegated subnets will be created.

Network Security
- Public network access disabled
- Private endpoints for all services
- Network ACLs with deny by default

**Network Infrastructure**
- A Virtual Network (192.168.0.0/16) is created (if existing isn't passed in)
- Agent Subnet (192.168.0.0/24): Hosts Agent client
- Private endpoint Subnet (192.168.1.0/24): Hosts private endpoints
- MCP Subnet (192.168.2.0/24): Hosts MCP servers, OpenAPI tools, Azure Functions, and A2A agents

**Private Endpoints**
Private endpoints ensure secure, internal-only connectivity. Private endpoints are created for the following:
- Microsoft Foundry
- Azure AI Search
- Azure Storage
- Azure Cosmos DB
- Azure Monitor Private Link Scope (AMPLS) — enables telemetry export from hosted agents

**Private DNS Zones**
| Private Link Resource Type | Sub Resource | Private DNS Zone Name | Public DNS Zone Forwarders |
|----------------------------|--------------|------------------------|-----------------------------|
| **Microsoft Foundry**       | account      | `privatelink.cognitiveservices.azure.com`<br>`privatelink.openai.azure.com`<br>`privatelink.services.ai.azure.com` | `cognitiveservices.azure.com`<br>`openai.azure.com`<br>`services.ai.azure.com` |
| **Azure AI Search**        | searchService| `privatelink.search.windows.net` | `search.windows.net` |
| **Azure Cosmos DB**        | Sql          | `privatelink.documents.azure.com` | `documents.azure.com` |
| **Azure Storage**          | blob         | `privatelink.blob.core.windows.net` | `blob.core.windows.net` |
| **Azure Monitor (AMPLS)**  | azuremonitor | `privatelink.monitor.azure.com`<br>`privatelink.oms.opinsights.azure.com`<br>`privatelink.ods.opinsights.azure.com`<br>`privatelink.agentsvc.azure-automation.net` | `monitor.azure.com`<br>`oms.opinsights.azure.com`<br>`ods.opinsights.azure.com`<br>`agentsvc.azure-automation.net` |

### Authentication & Authorization

- **Managed Identity**
  - Zero-trust security model
  - No credential storage
  - Platform-managed rotation

  This template uses System Managed Identity, but User Assigned Managed Identity is also supported.

- **Role Assignments**
  - **Azure AI Search**
    - Search Index Data Contributor (`8ebe5a00-799e-43f5-93ac-243d3dce84a7`)
    - Search Service Contributor (`7ca78c08-252a-4471-8644-bb5ff32d4ba0`)
  - **Azure Storage Account**
    - Storage Blob Data Owner (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`)
    - Storage Queue Data Contributor (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`) (if Azure Function tool enabled)
    - Two containers will automatically be provisioned during the project create capability host process:
      - Azure Blob Storage Container: `<workspaceId>-azureml-blobstore`
        - Storage Blob Data Contributor
      - Azure Blob Storage Container: `<workspaceId>-agents-blobstore`
        - Storage Blob Data Owner
  - **Cosmos DB for NoSQL**
    - Cosmos DB Operator (`230815da-be43-4aae-9cb4-875f7bd000aa`)
    - Cosmos DB Built-in Data Contributor
    - Three containers will automatically be provisioned during the create capability host process:
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-thread-message-store`
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-system-thread-message-store`
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-agent-entity-store`

---

## Connecting to a Private Foundry Resource

When public network access is disabled (the default), you need a secure connection to reach the Foundry resource. Azure provides three methods:

1. **Azure VPN Gateway** — Connect from your local network to the Azure VNet over an encrypted tunnel.
2. **Azure ExpressRoute** — Use a private, dedicated connection from your on-premises infrastructure to Azure.
3. **Azure Bastion** — Use a jump box VM on the VNet, accessed securely through the Azure portal.

For detailed setup instructions, see: [Securely connect to Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?view=foundry#securely-connect-to-foundry).

## Private MCP Evidence Checklist

When troubleshooting private MCP connectivity, confirm the following. SDK test steps are in [TESTING-GUIDE.md](tests/TESTING-GUIDE.md).

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

## Testing Agents with Private Resources

### Option 1: Portal Testing

If the Foundry resource has **public network access enabled**, you can test directly in the portal:

1. Navigate to [Azure AI Foundry portal](https://ai.azure.com)
2. Select your project
3. Create an agent with AI Search tool
4. Test that the agent can query the private AI Search index

If the Foundry resource has **public network access disabled** (default), you need to connect via VPN Gateway, ExpressRoute, or Azure Bastion before accessing the portal. See [Connecting to a Private Foundry Resource](#connecting-to-a-private-foundry-resource).

### Option 2: SDK Testing

See [tests/TESTING-GUIDE.md](tests/TESTING-GUIDE.md) for detailed SDK testing instructions.

---

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

> **Note on `--ingress external`**: App-level `--ingress external` is external to the app within the Container Apps environment boundary. It does **not** create an internet-reachable endpoint when the environment is `--internal-only` and public network access is disabled. Internal Container Apps environments have no public endpoint — the FQDN only resolves within the VNet.

Then configure private DNS zone for Container Apps (see TESTING-GUIDE.md Step 4.4).

  - **Azure Monitor (Application Insights)**
    - Log Analytics Reader (`73c42c96-874c-492b-b04d-ab87d138a893`) — read the agent trace/telemetry data
    - Privileged Monitoring Data Reader (`dbc9c667-e97f-4491-aee6-90b9cf960190`) — required to read GenAI prompt/response content

---

## Module Structure

```text
modules-network-secured/
├── add-project-capability-host.bicep               # Configuring the project's capability host
├── ai-account-identity.bicep                       # Microsoft Foundry deployment and configuration
├── ai-project-identity.bicep                       # Foundry project deployment and connection configuration
├── ai-project-identity-unique.bicep                # Modified project module with unique connection names
├── ai-search-role-assignments.bicep                # AI Search RBAC configuration
├── application-insights.bicep                      # Workspace-based Application Insights for agent tracing
├── application-insights-role-assignment.bicep     # Application Insights RBAC (project MI trace/GenAI read access)
├── azure-storage-account-role-assignment.bicep     # Storage Account RBAC configuration
├── blob-storage-container-role-assignments.bicep   # Blob Storage Container RBAC configuration
├── blob-storage-container-role-assignments-unique.bicep # Modified storage role assignment module
├── cosmos-container-role-assignments.bicep         # CosmosDB container Account RBAC configuration
├── cosmosdb-account-role-assignment.bicep          # CosmosDB Account RBAC configuration
├── existing-vnet.bicep                             # Bring your existing virtual network to template deployment
├── format-project-workspace-id.bicep               # Formatting the project workspace ID
├── monitor-private-link-scope.bicep                # Azure Monitor Private Link Scope (AMPLS) for private telemetry ingestion
├── network-agent-vnet.bicep                        # Logic for routing virtual network set-up if existing virtual network is selected
├── private-endpoint-and-dns.bicep                  # Creating virtual networks and DNS zones.
├── standard-dependent-resources.bicep              # Deploying CosmosDB, Storage, and Search
├── subnet.bicep                                    # Setting the subnet for Agent network injection
├── validate-existing-resources.bicep               # Validate existing CosmosDB, Storage, and Search to template deployment
└── vnet.bicep                                      # Deploying a new virtual network
```

## Maintenance

### Regular Tasks

1. Review role assignments
2. Monitor network security
3. Check service health
4. Update configurations as needed

### Troubleshooting

1. Verify private endpoint connectivity
2. Check DNS resolution
3. Validate role assignments
4. Review network security groups

---

## References

- [Microsoft Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Microsoft Foundry RBAC Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
