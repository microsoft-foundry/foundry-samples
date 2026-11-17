---
description: This template demonstrates how to set up Azure AI Foundry with a basic agent configuration using VNet injection for network isolation.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-basic-agent-vnet
languages:
- bicep
- json
---

# Microsoft Foundry: Basic Agent Setup with E2E Network Isolation

> **NEW**
> For support on deploying the right network isolation template, check out the [GitHub Copilot for Azure skill for private networking](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/resource/private-network/private-network.md) set-up!

---

## Overview

This infrastructure-as-code (IaC) solution deploys a **basic agent** environment with **VNet injection** for network isolation. Unlike the [standard agent setup (template 15)](../15-private-network-standard-agent-setup), this template does **not** create or connect BYO (Bring Your Own) resources such as Azure AI Search, Azure Storage Account, or Azure Cosmos DB. Instead, it relies on platform-managed resources for agent storage needs.

This template combines:
- **Basic agent configuration** — No BYO resources, no connections to external search/storage/cosmos services
- **VNet injection** — Custom virtual network with subnet delegation for agent workloads (`Microsoft.App/environments`)
- **Private endpoints** — Network-secured access to the AI Services account only
- **Capability host** — Uses the platform-managed basic agent capability host without BYO connections; explicit creation is opt-in

### What Gets Deployed

| Resource | Purpose |
|----------|---------|
| **Virtual Network** | Network isolation with two subnets |
| **Agent Subnet** | Delegated to `Microsoft.App/environments` for VNet-injected agent workloads |
| **Private Endpoint Subnet** | Hosts private endpoint for the AI Services account |
| **AI Services Account** | AI Foundry account with network injection, public access disabled |
| **Private Endpoint** | Secure private connectivity to AI Services |
| **Private DNS Zones** (x3) | DNS resolution for `privatelink.services.ai.azure.com`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com` |
| **AI Foundry Project** | Project with system-assigned managed identity |
| **Capability Host** | Platform-managed basic agent capability host; the template does not create an additional host by default |
| **Model Deployment** | gpt-4.1 (configurable) |
| **Azure Container Registry** *(optional)* | Premium SKU ACR with private endpoint, DNS zone (`privatelink.azurecr.io`), and AcrPull role for the project identity |


[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F11-private-network-basic-vnet%2Fmain.json)

---

## When to Use This Template

Use this template when you need:
- **VNet injection for network isolation** — Agent workloads run inside your own virtual network with subnet delegation
- **Basic agent setup without BYO resources** — Platform-managed storage for agent data (no customer-managed Storage, Cosmos DB, or AI Search)
- **Private endpoint access to AI Services** — Secure, internal-only connectivity to the Foundry account
- **System Assigned Managed Identity** — Simplified identity management with platform-managed credentials

### Template Decision Guide

Use the table below to choose the right infrastructure template for your scenario:

| Template | Agent Type | Networking | Identity | Key Use Case |
|----------|-----------|------------|----------|-------------|
| [**11** (this template)](../11-private-network-basic-vnet/) | **Basic** (platform-managed) | BYO VNet injection | System Assigned MI | Basic agents with VNet isolation — no BYO resources needed |
| [**15**](../15-private-network-standard-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | E2E network isolation with full agent capabilities |
| [**19**](../19-private-network-agent-tools/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** tools behind VNet (MCP, OpenAPI, Functions, A2A) |
| [**17**](../17-private-network-standard-user-assigned-identity-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | **User Assigned MI** | Same as 15 but with user-managed identity |
| [**16**](../16-private-network-standard-agent-apim-setup-preview/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** private APIM integration (preview) |
| [**18**](../18-managed-virtual-network-preview/) | Standard (BYO resources) | **Managed VNet** (Microsoft-managed) | System Assigned MI | Network isolation without managing your own VNet (preview) |
| [**15a**](../15a-private-network-evaluation-only-setup/) | Evaluation only | BYO VNet + Private Endpoints | System Assigned MI | Minimal setup for evaluation — no Cosmos DB, AI Search, or capability host |
| [**41**](../41-standard-agent-setup/) | Standard (BYO resources) | **Public** (no VNet) | System Assigned MI | Standard agents without network isolation |
| [**40**](../40-basic-agent-setup/) | **Basic** (platform-managed) | **Public** (no VNet) | System Assigned MI | Simplest setup — no BYO resources, no private networking |

---

## Key Information

**Region and Resource Placement Requirements**
- **All Foundry workspace resources should be in the same region as the VNet**, including the Foundry Account and Project. The only exception is within the Foundry Account, you may choose to deploy your model to a different region, and any cross-region communication will be handled securely within our network infrastructure.
  - **Note:** Your Virtual Network can be in a different resource group than your Foundry workspace resources

---

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
   - **Foundry Account Owner**: Needed to create the Azure AI Foundry account and project.
   - **Owner or Role Based Access Administrator**: Needed to assign RBAC on the Azure resources used by this template.
   - **Foundry User**: Needed to create and use agents, projects, or evaluation workloads after deployment.

2. **Register Resource Providers**

   Make sure you have an active Azure subscription that allows registering resource providers. Subnet delegation requires the Microsoft.App provider to be registered in your subscription. If it's not already registered, run the commands below:

   ```bash
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.App'
   ```

3. Network administrator permissions (if operating in a restricted or enterprise environment)

4. Sufficient quota for all resources required by this template in the target Azure region, including model deployment quota.

5. Azure CLI installed and configured on your local workstation or deployment pipeline server

---

## Pre-Deployment Steps

### Networking Requirements

1. Review network requirements and plan Virtual Network address space (e.g., `192.168.0.0/16` or an alternative non-overlapping address space)

2. Two subnets are needed:
   - **Agent Subnet** (e.g., `192.168.0.0/24`): Hosts Agent client for Agent workloads, delegated to `Microsoft.App/environments`. The recommended size should be `/24` for this delegated subnet.
   - **Private Endpoint Subnet** (e.g., `192.168.1.0/24`): Hosts private endpoints for the AI Services account
  - Ensure that the address spaces for the used VNET does not overlap with any existing networks in your Azure environment or reserved IP ranges like the following: `169.254.0.0/16, 172.30.0.0/16, 172.31.0.0/16, 192.0.2.0/24, 0.0.0.0/8, 127.0.0.0/8, 100.100.0.0/17, 100.100.192.0/19, 100.100.224.0/19`. This includes all address space(s) you have in your VNET if you have more than one, and peered VNETs.

  > **Notes:** 
  - If you do not provide an existing virtual network, the template will create a new virtual network with the default address spaces and subnets described above. If you use an existing virtual network, make sure it already contains two subnets (Agent and Private Endpoint) before deploying the template.
  - Basic setups use the platform-managed capability host. Leave `createProjectCapabilityHost` set to `false` for normal deployments. Enable explicit creation only when the project has no capability host; each project supports only one host, so creating or renaming an additional host causes a conflict.
  - You must ensure the subnet is exclusively delegated to __Microsoft.App/environments__ and cannot be used by any other Azure resources.

### Limitations / Known Issues

1. The delegated agent subnet must be exclusively used by a single Foundry account. It cannot be shared across accounts.
2. The Foundry resource and the virtual network must be in the same Azure region.
3. Use only supported RFC 1918 or RFC 6598 address space. For RFC 1918, use addresses within `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`. For RFC 6598 (CGNAT), use addresses within `100.64.0.0/10`, excluding `100.100.0.0/17`, `100.100.192.0/19`, and `100.100.224.0/19`. Public IP ranges aren't supported.
4. This template uses platform-managed resources for agent storage. If you need customer-managed Storage, Cosmos DB, or AI Search, use [template 15](../15-private-network-standard-agent-setup/) instead.
5. There is no upgrade path from BYO VNet (this template) to Managed Virtual Network (template 18). A Foundry resource redeployment is required.
6. All projects within the same Foundry account share model deployments. Per-project model isolation is not supported.

### Account Deletion Prerequisites and Cleanup Guidance

Before deleting an **Account** resource, it is essential to first delete the associated **Account Capability Host**. Failure to do so may result in residual dependencies—such as subnets and other provisioned resources (e.g., ACA applications)—remaining linked to the capability host. This can lead to errors such as **"Subnet already in use"** when attempting to reuse the same subnet in a different account deployment.

**Cleanup Options**

**1. Full Account Removal**: To completely remove an account, you must delete and purge the account. Simply deleting the account is not sufficient, you must purge so that deletion of the associated capability host is triggered. The service will automatically handle the removal of the capability host and any linked resources in the background. To purge the account, use the following [link](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource). Please allow approximately max of 20 minutes for all resources to be fully unlinked from the account.

**2. Retain Account, Remove Capability Host**: If you intend to retain the account but remove the capability host, execute the script `deleteCaphost.sh` located in the [template 15 folder](../15-private-network-standard-agent-setup/). After deletion, allow approximately max of 20 minutes for all resources to be fully unlinked from the account. To recreate the capability host for the account, use the script `createCaphost.sh` located in the same folder.

> **Important**: Before deleting the account capability host, ensure that the **project capability host** is deleted.

### Template Customization

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
| `dnsZonesSubscriptionId` | Subscription ID for existing DNS zones | `''` (current sub) | No |
| `existingDnsZones` | Map of DNS zone names to resource groups | All empty (creates new) | No |
| `createProjectCapabilityHost` | Explicitly create a project capability host. Leave disabled for basic setups using the platform-managed host; enable only when the project has no capability host. | `false` | No |
| `projectCapHost` | Name of the project capability host, used only when `createProjectCapabilityHost` is `true` | `caphostproj` | No |
| `enableContainerRegistry` | When `true`, creates an Azure Container Registry (Premium SKU) with a private endpoint in the PE subnet, a `privatelink.azurecr.io` DNS zone, and an AcrPull role assignment for the project managed identity. | `true` | No |
| `developerIpCidr` | Developer IP CIDR to allowlist for ACR push access (e.g., `203.0.113.0/26`). When set, enables public network access with a deny-all default + an IP allowlist rule so developers can push images. When empty, public access remains fully disabled. | `''` | No |

#### BYO Virtual Network Details

**Use an Existing Virtual Network and Subnets**

To use an existing VNet and subnets, set the `existingVnetResourceId` parameter to the full Azure Resource ID of the target VNet, and provide the names of the two required subnets. If the existing VNet is associated with private DNS zones, set the `existingDnsZones` parameter to the resource group name in which the zones are located. For example:
- `param existingVnetResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>"`
- `param agentSubnetName string = 'agent-subnet'` (optional, default is `agent-subnet`)
- `param agentSubnetPrefix string = '192.168.0.0/24'` (optional, default is `192.168.0.0/24`)
- `param peSubnetName string = 'pe-subnet'` (optional, default is `pe-subnet`)
- `param peSubnetPrefix string = '192.168.1.0/24'` (optional, default is `192.168.1.0/24`)
- `param dnsZonesSubscriptionId string = ''` (optional, leave empty to use current subscription, or set to a subscription ID if DNS zones are in a different subscription)
- `param existingDnsZones = {`
  `'privatelink.services.ai.azure.com': 'privzoneRG'` (add resource group name where your private DNS zone is located)
  `'privatelink.openai.azure.com': ''` (leave empty to create new private DNS zone)
  `'privatelink.cognitiveservices.azure.com': ''`
  `'privatelink.azurecr.io': ''` `}`

The optional `privatelink.azurecr.io` entry is used when `enableContainerRegistry` is `true`. Leave it empty or omit it to create a new ACR private DNS zone; supply a resource group name to reuse an existing zone.

> **Tip**: If subnet information is provided, make sure the subnets exist within the specified VNet to avoid deployment errors. If subnet information is not provided, the template will create subnets with the default address space.

> **Cross-Subscription DNS Zones**: All DNS zones specified in `existingDnsZones` will be referenced from the subscription specified in `dnsZonesSubscriptionId`. Leave this parameter empty (default) to use the current deployment subscription, or set it to a subscription ID if your DNS zones are located in a different subscription.

> **Important**: When `dnsZonesSubscriptionId` is set to a different subscription, ALL DNS zones in `existingDnsZones` must have resource groups specified (non-empty values). The template does not support creating new DNS zones in a different subscription. Empty resource groups are only allowed when creating zones in the current deployment subscription.

---

## Deployment Steps

Choose your deployment method: Use the "Deploy to Azure" button from the top of this README for a guided experience in Azure Portal.

### Option 1: Automatic deployment
Click the Deploy to Azure button above to open the Azure portal and deploy the template directly.
- Fill in the parameters as needed, including the existing VNet and subnets if applicable.

### Option 2: Deploy via Azure CLI

- **Create a New (or Use Existing) Resource Group**

   ```bash
   az group create --name <new-rg-name> --location <your-selected-region>
   ```

- Deploy the main.bicep file
  - Edit the main.bicepparam file to use an existing Virtual Network & subnets if needed.

   ```bash
   az deployment group create \
     --resource-group <new-rg-name> \
     --template-file main.bicep \
     --parameters main.bicepparam
   ```

   Or deploy with inline parameters:

   ```bash
   az deployment group create \
     --resource-group <new-rg-name> \
     --template-file main.bicep \
     --parameters aiServices=myFoundry location=eastus
   ```

### Option 3: Use an Existing Virtual Network

If you already have a VNet you want to use, provide its resource ID:

```bash
az deployment group create \
  --resource-group <new-rg-name> \
  --template-file main.bicep \
  --parameters main.bicepparam \
  --parameters existingVnetResourceId='/subscriptions/<sub-id>/resourceGroups/<rg-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>'
```

The template will create the required subnets (agent subnet with delegation and PE subnet) in your existing VNet.

---

## Post-Deployment

**NOTE:** To access your Foundry resource securely, please use either a VM, VPN, or ExpressRoute since public network access is disabled.

### Cleanup

To delete all resources created by this template:

```bash
az group delete --name <your-resource-group> --yes --no-wait
```

> **Important**: If you need to reuse the same subnet, follow the [Account Deletion Prerequisites and Cleanup Guidance](#account-deletion-prerequisites-and-cleanup-guidance) to properly purge the account and wait for the capability host to fully unlink (~20 minutes).

---

## Network Secured Basic Agent Architecture Deep Dive

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
                    │  │ ┌────────┐            │   │
                    │  │ │Foundry │            │   │  ◄── Private endpoint
                    │  │ └────────┘            │   │      (no public access)
                    │  └──────────────────────┘    │
                    └──────────────────────────────┘
```

### Core Components

**Microsoft Foundry** resource
- Central orchestration point
- Manages service connections
- Set networking and policy configurations

**Foundry** project
- Defines the workspace configuration
- Service integration
- Agents are created within a specific project, and each project acts as an isolated workspace. This means:
  - All agents in the same project share access to platform-managed storage resources.
  - Data is isolated between projects. Agents in one project cannot access resources from another. Projects are currently the unit of sharing and isolation in Foundry. See the what is AI foundry article for more information on Foundry projects.

**Platform-Managed Resources**: In the basic agent setup, all agent state (thread storage, file storage, vector store) is managed by the platform. No customer-managed BYO resources are required.

### Azure Resources Created

**Microsoft Foundry (Cognitive Services)**
- Type: `Microsoft.CognitiveServices/accounts`
- API version: `2025-04-01-preview`
- Kind: AIServices
- SKU: S0
- Identity: System-assigned
- Features:
  - Custom subdomain name
  - Disabled public network access
  - Network ACLs with Azure Services bypass
  - Network injection with agent subnet delegation

**AI Model Deployment**
- Type: `Microsoft.CognitiveServices/accounts/deployments`
- API version: `2025-04-01-preview`
- SKU: Based on `modelSkuName` parameter, capacity set by `modelCapacity`
- Model properties:
  - Name: From `modelName` parameter
  - Format: From `modelFormat` parameter
  - Version: From `modelVersion` parameter

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

This implementation utilizes a BYO VNet (Bring Your Own Virtual Network) approach with subnet delegation. Within your virtual network, two subnets are created: one delegated for agent workloads and one for private endpoints.

**Network Security**
- Public network access disabled
- Private endpoint for AI Services
- Network ACLs with deny by default

**Network Infrastructure**
- A Virtual Network (192.168.0.0/16) is created (if existing isn't passed in)
- Agent Subnet (192.168.0.0/24): Hosts Agent client, delegated to `Microsoft.App/environments`
- Private Endpoint Subnet (192.168.1.0/24): Hosts private endpoint for AI Services

**Private Endpoints**
A private endpoint ensures secure, internal-only connectivity to the AI Services account.

**Private DNS Zones**
| Private Link Resource Type | Sub Resource | Private DNS Zone Name | Public DNS Zone Forwarders |
|----------------------------|--------------|------------------------|-----------------------------|
| **Microsoft Foundry** | account | `privatelink.cognitiveservices.azure.com`<br>`privatelink.openai.azure.com`<br>`privatelink.services.ai.azure.com` | `cognitiveservices.azure.com`<br>`openai.azure.com`<br>`services.ai.azure.com` |
| **Azure Monitor (AMPLS)** | azuremonitor | `privatelink.monitor.azure.com`<br>`privatelink.oms.opinsights.azure.com`<br>`privatelink.ods.opinsights.azure.com`<br>`privatelink.agentsvc.azure-automation.net` | `monitor.azure.com`<br>`oms.opinsights.azure.com`<br>`ods.opinsights.azure.com`<br>`agentsvc.azure-automation.net` |

### Authentication & Authorization

- **Managed Identity**
  - Zero-trust security model
  - No credential storage
  - Platform-managed rotation

  This template uses System Managed Identity.

> **Note**: Unlike the standard agent setup (template 15), this basic template does not create RBAC role assignments for BYO resources (Storage, Cosmos DB, AI Search), since those resources are not used.

---

## Module Structure

```text
modules-network-secured/
├── ai-account-identity.bicep                   # AI Services account with network injection
├── add-project-capability-host.bicep            # Basic capability host (no BYO connections)
├── application-insights.bicep                   # Workspace-based Application Insights for agent tracing
├── monitor-private-link-scope.bicep             # Azure Monitor Private Link Scope (AMPLS) for private telemetry ingestion
├── network-agent-vnet.bicep                     # VNet router (new or existing)
├── vnet.bicep                                   # New VNet creation
├── existing-vnet.bicep                          # Existing VNet integration
├── subnet.bicep                                 # Subnet creation helper
└── private-endpoint-and-dns.bicep               # PE and DNS for AI Services only
```

### Compared to Other Templates

| Feature | 10 (Private Network Basic) | **11 (This Template)** | 15 (Standard Agent Setup) |
|---------|---------------------------|------------------------|---------------------------|
| Public Network Access | Disabled | Disabled | Disabled |
| VNet Injection | No | **Yes** | Yes |
| Agent Subnet Delegation | No | **Yes** (`Microsoft.App/environments`) | Yes |
| Private Endpoints | AI Services only | **AI Services only** | AI Services + Search + Storage + Cosmos DB |
| BYO Resources | No | **No** | Yes (Search, Storage, Cosmos DB) |
| Capability Host | No | **Yes (basic)** | Yes (with BYO connections) |
| Existing VNet Support | No | **Yes** | Yes |
| RBAC Assignments | No | **No** | Yes (Storage, Cosmos, Search) |

---

## Maintenance

### Regular Tasks

1. Monitor network security
2. Check service health
3. Review DNS resolution
4. Update configurations as needed

### Troubleshooting

1. Verify private endpoint connectivity
2. Check DNS resolution for AI Services
3. Validate subnet delegation is correct
4. Review network security groups

---

## References

- [Microsoft Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
