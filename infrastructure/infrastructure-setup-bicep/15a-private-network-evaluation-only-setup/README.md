---
description: This set of templates demonstrates how to set up a network-secured Microsoft Foundry environment for evaluation and data-generation scenarios without Cosmos DB or AI Search.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-evaluation-only
languages:
- bicep
- json
---

# Microsoft Foundry: Evaluation-Only Setup with Network Isolation


> **NEW**
> For support on deploying the right network isolation template, check out the [GitHub Copilot for Azure skill for private networking](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/resource/private-network/private-network.md) set-up!

> **IMPORTANT**
> 
> This template is a simplified version of the [standard agent setup](../15-private-network-standard-agent-setup/) designed for **evaluation and data-generation scenarios**. It does **not** deploy Cosmos DB or AI Search. It deploys workspace-based Application Insights (with private ingestion) for evaluation/agent tracing and an optional project capability host (Agents kind, no BYO connections) for data-generation. If you need full agent capabilities (thread storage in Cosmos DB, vector search in AI Search, stateful agents), use the standard agent setup instead.

---
## Overview
This infrastructure-as-code (IaC) solution deploys a **minimal** network-secured Microsoft Foundry environment with private networking and role-based access control (RBAC), intended for evaluation, testing, and data-generation purposes.

Unlike the full standard agent setup, this template:
- **Does NOT** create an Azure Cosmos DB account (no thread/conversation storage)
- **Does NOT** create an Azure AI Search resource (no vector stores)

What it **does** deploy:
- Azure AI Services account with a model deployment
- An AI Foundry project with a storage connection
- An Azure Storage account (or uses an existing one)
- Workspace-based Application Insights (Log Analytics + component) connected to the account for evaluation/agent tracing, with private ingestion via an Azure Monitor Private Link Scope
- An optional project capability host (`deployCapabilityHost`, enabled by default; Agents kind, no BYO connections) for data-generation workloads that use the hosted-agent runtime
- A VNet with private endpoints for AI Services and Storage
- Private DNS zones for secure name resolution
- RBAC role assignments for the project on the storage account and on Application Insights

---

## When to Use This Template

Use this template when you need:
- **Evaluation and testing only** — Run model evaluations without deploying full agent infrastructure
- **Minimal private networking** — Private endpoints for AI Services and Storage only (no Cosmos DB or AI Search)
- **Lower cost** — Fewer resources deployed compared to the full standard agent setup
- **Quick iteration** — Faster deployment time with a smaller resource footprint

### Template Decision Guide

Use the table below to choose the right infrastructure template for your scenario:

| Template | Agent Type | Networking | Identity | Key Use Case |
|----------|-----------|------------|----------|-------------|
| [**15a** (this template)](../15a-private-network-evaluation-only-setup/) | Evaluation + data generation | BYO VNet + Private Endpoints | System Assigned MI | Minimal setup for evaluation/datagen — App Insights + project capability host (no BYO connections); no Cosmos DB or AI Search |
| [**15**](../15-private-network-standard-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | E2E network isolation with full agent capabilities |
| [**19**](../19-private-network-agent-tools/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** tools behind VNet (MCP, OpenAPI, Functions, A2A) |
| [**17**](../17-private-network-standard-user-assigned-identity-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | **User Assigned MI** | Same as 15 but with user-managed identity |
| [**16**](../16-private-network-standard-agent-apim-setup-preview/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** private APIM integration (preview) |
| [**18**](../18-managed-virtual-network-preview/) | Standard (BYO resources) | **Managed VNet** (Microsoft-managed) | System Assigned MI | Network isolation without managing your own VNet (preview) |
| [**11**](../11-private-network-basic-vnet/) | **Basic** (platform-managed) | BYO VNet injection | System Assigned MI | Basic agents with VNet isolation — no BYO resources needed |
| [**41**](../41-standard-agent-setup/) | Standard (BYO resources) | **Public** (no VNet) | System Assigned MI | Standard agents without network isolation |
| [**40**](../40-basic-agent-setup/) | **Basic** (platform-managed) | **Public** (no VNet) | System Assigned MI | Simplest setup — no BYO resources, no private networking |

---

## Deploy to Azure


[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F15a-private-network-evaluation-only-setup%2Fazuredeploy.json)

---

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
  - **Foundry Account Owner**: Needed to create the Microsoft Foundry account and project.
  - **Owner or Role Based Access Administrator**: Needed to assign RBAC on the Azure resources used by this template.
  - **Foundry User**: Needed to create and use agents, projects, or evaluation workloads after deployment.
  In this template, the required RBAC assignments apply only to the storage account.

1. **Register Resource Providers**

   Make sure you have an active Azure subscription that allows registering resource providers. For example, subnet delegation requires the Microsoft.App provider to be registered in your subscription. If it's not already registered, run the commands below:

   ```bash
   az provider register --namespace 'Microsoft.KeyVault'
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Storage'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.App'
   az provider register --namespace 'Microsoft.ContainerService'
   ```

1. Network administrator permissions (if operating in a restricted or enterprise environment)

1. Sufficient quota for all resources required by this template in the target Azure region, including model deployment quota.
    * If no parameters are passed in, this template creates an Microsoft Foundry resource, Foundry project, and Azure Storage account

1. Azure CLI installed and configured on your local workstation or deployment pipeline server

---

## Pre-Deployment Steps

### Networking Requirements
1. Review network requirements and plan Virtual Network address space (e.g., 192.168.0.0/16 or an alternative non-overlapping address space)

2. Two subnets are needed:  
    - **Agent Subnet** (e.g., 192.168.0.0/24): Hosts Agent client for workloads, delegated to Microsoft.App/environments. The recommended size should be /24 for this delegated subnet.
    - **Private endpoint Subnet** (e.g., 192.168.1.0/24): Hosts private endpoints 
    - Ensure that the address spaces for the used VNET does not overlap with any existing networks in your Azure environment or reserved IP ranges like the following: 169.254.0.0/16,172.30.0.0/16,172.31.0.0/16,192.0.2.0/24,0.0.0.0/8,127.0.0.0/8,100.100.0.0/17,100.100.192.0/19,100.100.224.0/19.
    This includes all address space(s) you have in your VNET if you have more than one, and peered VNETs.
  
  > **Notes:** 
  - If you do not provide an existing virtual network, the template will create a new virtual network with the default address spaces and subnets described above.
  - You must ensure the subnet is not already in use by another account.
  - You must ensure the subnet is exclusively delegated to __Microsoft.App/environments__ and cannot be used by any other Azure resources.
  - Your Foundry resource and the virtual network created for delegation must be in the same region.

### Limitations / Known Issues

1. The delegated agent subnet must be exclusively used by a single Foundry account. It cannot be shared across accounts.
2. The Foundry resource and the virtual network must be in the same Azure region.
3. Use only supported RFC 1918 or RFC 6598 address space. For RFC 1918, use addresses within `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`. For RFC 6598 (CGNAT), use addresses within `100.64.0.0/10`, excluding `100.100.0.0/17`, `100.100.192.0/19`, and `100.100.224.0/19`. Public IP ranges aren't supported.
4. This template does **not** deploy Cosmos DB or AI Search. The project capability host it creates has **no BYO connections**, so stateful agents that need thread storage (Cosmos DB) or vector search (AI Search) are not supported. Use [template 15](../15-private-network-standard-agent-setup/) for full agent capabilities.
5. There is no upgrade path from this evaluation template to the full standard agent setup. A redeployment with template 15 is required.

### Template Customization

Note: If not provided, the following resources will be created automatically for you:
- VNet and two subnets
- Azure Storage
- Azure Container Registry (Premium SKU) with private endpoint *(when `enableContainerRegistry=true`)*

#### Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `location` | Azure region for deployment | `eastus` | Yes |
| `aiServices` | Base name for the AI Services resource | `aiservices` | No |
| `firstProjectName` | Name for the Foundry project | `project` | No |
| `modelName` | Model to deploy | `gpt-4.1` | No |
| `modelFormat` | Model provider | `OpenAI` | No |
| `modelVersion` | Model version | `2025-04-14` | No |
| `modelSkuName` | Model deployment SKU | `GlobalStandard` | No |
| `modelCapacity` | Tokens per minute (TPM) capacity | `30` | No |
| `vnetName` | Virtual Network name | `agent-vnet-test` | No |
| `agentSubnetName` | Subnet name for agent workloads | `agent-subnet` | No |
| `agentSubnetPrefix` | Address prefix for agent subnet | `192.168.0.0/24` | No |
| `peSubnetName` | Subnet name for private endpoints | `pe-subnet` | No |
| `peSubnetPrefix` | Address prefix for PE subnet | `192.168.1.0/24` | No |
| `existingVnetResourceId` | Full ARM Resource ID of an existing VNet | `''` (creates new) | No |
| `vnetAddressPrefix` | Address space for new VNet | `192.168.0.0/16` | No |
| `azureStorageAccountResourceId` | ARM Resource ID of existing Storage account | `''` (creates new) | No |
| `dnsZonesSubscriptionId` | Subscription ID for existing DNS zones | `''` (current sub) | No |
| `existingDnsZones` | Map of DNS zone names to resource groups | All empty (creates new) | No |
| `enableContainerRegistry` | When `true`, creates an Azure Container Registry (Premium SKU) with a private endpoint in the PE subnet, a `privatelink.azurecr.io` DNS zone, and an AcrPull role assignment for the project managed identity. | `true` | No |
| `developerIpCidr` | Developer IP CIDR to allowlist for ACR push access (e.g., `203.0.113.0/26`). When set, enables public network access with a deny-all default + an IP allowlist rule so developers can push images. When empty, public access remains fully disabled. | `''` | No |

#### BYO Resource Details

1. **Use Existing Virtual Network and Subnets**

To use an existing VNet and subnets, set the `existingVnetResourceId` parameter to the full Azure Resource ID of the target VNet:
- param existingVnetResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>"
- param agentSubnetName string = 'agent-subnet' //optional, default is 'agent-subnet'
- param agentSubnetPrefix string = '192.168.0.0/24' //optional, default is '192.168.0.0/24'
- param peSubnetName string = 'pe-subnet' //optional, default is 'pe-subnet'
- param peSubnetPrefix string = '192.168.1.0/24' //optional, default is '192.168.1.0/24'
- param dnsZonesSubscriptionId string = '' //optional, leave empty to use current subscription
- param existingDnsZones = {
       
         'privatelink.services.ai.azure.com': 'privzoneRG' //add resource group name where your private DNS zone is located
       
         'privatelink.openai.azure.com': '' //Leave empty to create new private dns zone... }

💡 If subnets information is provided then make sure it exist within the specified VNet to avoid deployment errors. If subnet information is not provided, the template will create subnets with the default address space.

2. **Use an existing Azure Storage account**

To use an existing Azure Storage account, set the azureStorageAccountResourceId parameter to the full Azure resource Id:
- param azureStorageAccountResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}

---

## Deploy the bicep template

**Option 1: Manually deploy the bicep template**
- **Create a New (or Use Existing) Resource Group**

   ```bash
   az group create --name <new-rg-name> --location <your-rg-region>
   ```
- Deploy the main.bicep file

   ```bash
   az deployment group create --resource-group <your-resource-group> --template-file main.bicep --parameters main.bicepparam
   ```

> **Note:** To access a private Foundry resource securely, use one of the following:
> - A VM or jump box on the virtual network, optionally accessed through Azure Bastion
> - Azure VPN Gateway
> - Azure ExpressRoute

### Add a project capability host to an existing deployment

New deployments create a project capability host by default. If your existing network-injected template 15a project has no capability host, follow [Add a project capability host to template 15a](add-project-capability-host.md). The guide deploys only the standalone project capability host module, leaves the existing infrastructure unchanged, and covers host verification and service-managed DataProxy metadata.

This procedure is specific to template 15a, not the full standard agent setup in template 15.

### Cleanup

To delete all resources created by this template:

```bash
az group delete --name <your-resource-group> --yes --no-wait
```

---  

## Architecture Deep Dive

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
                    │  │   (Evaluation Only)     │  │
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
                    │  │ │Storage │ │Foundry │ │   │  ◄── Private endpoints
                    │  │ └────────┘ └────────┘ │   │      (no public access)
                    │  └──────────────────────┘    │
                    └──────────────────────────────┘
```

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

Foundry Project
- Type: Microsoft.CognitiveServices/accounts/projects
- Identity: System-assigned managed identity
- Connections: Storage account only (no Cosmos DB or AI Search connections)

Storage Account 
- Type: Microsoft.Storage/storageAccounts 
- Kind: StorageV2 
- SKU: ZRS or GRS (region dependent; use Standard_GRS if ZRS not available) 
- Features:
  - Blob service
  - Minimum TLS Version: 1.2
  - Block public blob access
  - Disabled public network access
  - Force Azure AD authentication (SharedKey access disabled) 

### Network Security Design

Network Security
- Public network access disabled
- Private endpoints for AI Services and Storage
- Network ACLs with deny by default

**Network Infrastructure**
- A Virtual Network (192.168.0.0/16) is created (if existing isn't passed in)
- Agent Subnet (192.168.0.0/24): Hosts Agent client
- Private endpoint Subnet (192.168.1.0/24): Hosts private endpoints

**Private Endpoints** 
Private endpoints ensure secure, internal-only connectivity. Private endpoints are created for:
- Microsoft Foundry (account)
- Azure Storage (blob)

**Private DNS Zones**
| Private Link Resource Type | Sub Resource | Private DNS Zone Name | Public DNS Zone Forwarders |
|----------------------------|--------------|------------------------|-----------------------------|
| **Microsoft Foundry**       | account      | `privatelink.cognitiveservices.azure.com`<br>`privatelink.openai.azure.com`<br>`privatelink.services.ai.azure.com` | `cognitiveservices.azure.com`<br>`openai.azure.com`<br>`services.ai.azure.com` |
| **Azure Storage**          | blob         | `privatelink.blob.core.windows.net` | `blob.core.windows.net` |

### Authentication & Authorization

- **Managed Identity**
  - Zero-trust security model
  - No credential storage
  - Platform-managed rotation
  - This template uses System Managed Identity

- **Role Assignments**
  - **AI Services Account**
    - Foundry User (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) — grants the project MI data-plane access
  - **Azure Storage Account**
    - Storage Blob Data Contributor (`ba92f5b4-2d11-453d-a403-e96b0029c9fe`)
    - Storage Blob Data Owner (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`) — scoped to project containers

---

## Module Structure

```text
modules-network-secured/
├── ai-account-identity.bicep                       # Microsoft Foundry deployment and configuration
├── ai-account-role-assignment.bicep                # Foundry User role assignment on the account
├── ai-project-identity.bicep                       # Foundry project deployment with storage connection
├── azure-storage-account-role-assignment.bicep      # Storage Account RBAC configuration
├── blob-storage-container-role-assignments.bicep    # Blob Storage Container RBAC configuration
├── existing-vnet.bicep                             # Bring your existing virtual network
├── format-project-workspace-id.bicep               # Formatting the project workspace ID
├── network-agent-vnet.bicep                        # Logic for routing virtual network set-up
├── private-endpoint-and-dns.bicep                  # Private endpoints and DNS zones (AI Services + Storage only)
├── standard-dependent-resources.bicep              # Deploying Storage Account
├── subnet.bicep                                    # Setting the subnet
├── validate-existing-resources.bicep               # Validate existing Storage Account
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

## References

- [Configure private link for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Microsoft Foundry RBAC roles](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [Azure RBAC documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network security best practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
