---
description: This set of templates demonstrates how to set up Foundry Agent Service with virtual network isolation, where the project and account capability hosts are created implicitly from the project's capabilitySettings rather than declared as explicit resources.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent-capabilitysettings
languages:
- bicep
- json
---

# Microsoft Foundry: Network-Secured Agent Setup with capabilitySettings (Implicit Capability Hosts)

> **Scenario 22 — what differs from [template 15](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/15-private-network-standard-agent-setup)**
>
> This template is a derivative of the standard network-secured agent setup (template 15). It keeps the identical
> BYO VNet + private-endpoint networking, BYO Storage / Cosmos DB / AI Search, model deployment, ACR, and Azure Monitor
> private-link wiring. The **only** functional differences are:
>
> 1. **`capabilitySettings` on the project** — `modules-network-secured/ai-project-identity.bicep` sets
>    `properties.capabilitySettings = { documentStore: <cosmosId>, vectorStore: <searchId>, blobStore: <storageId> }`
>    (the BYO store ARM resource IDs). Declaring `capabilitySettings` makes AccountRP auto-provision the project's
>    connections and its capability host.
> 2. **No explicit capability-host resources** — both the project capability host
>    (`add-project-capability-host.bicep`) and the opt-in account capability host
>    (`add-account-capability-host.bicep`) modules have been **removed**. They are now **implicit resources**:
>    - The **account** capability host is created by the platform from `networkInjections.scenario='agent'` on the
>      account (`ai-account-identity.bicep`) — unchanged from template 15, just no opt-in override or
>      `createAccountCapabilityHost` flag.
>    - The **project** capability host is created by AccountRP from the project's `capabilitySettings`.
> 3. **Container-scoped role assignments are off by default** (`assignContainerRoles=false`). The implicit capability
>    host provisions the agent blob/thread containers and their data-plane role assignments during create, so the
>    template no longer pre-creates them. Set `assignContainerRoles=true` only to pre-assign against already-existing
>    containers.
>
> Everything else (account/project SMI roles for Cosmos DB Operator, Storage Blob Data Contributor, AI Search
> Index/Service Contributor, private endpoints, DNS, ACR, AMPLS) is identical to template 15.

> **NEW**
> For support on deploying the right network isolation template, check out the [GitHub Copilot for Azure skill for private networking](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/resource/private-network/private-network.md) set-up!

> **IMPORTANT**
> Please note this template does not support using Agent tools behind a VNET. Please refer to [template 19](../19-private-network-agent-tools/) and the [TESTING-GUIDE.md](../19-private-network-agent-tools/tests/TESTING-GUIDE.md) to ensure tool traffic also goes through your vnet.

---
## Overview
This infrastructure-as-code (IaC) solution deploys a network-secured agent environment with private networking and role-based access control (RBAC).

Standard setup supports private network isolation through utilizing **Bring Your Own Virtual Network (BYO VNet)** approach, also known as **custom VNet support with subnet delegation.** Please note this template does not support using Agent tools behind a VNET. Please use [template 19](../19-private-network-agent-tools/) for this.

This implementation gives you full control over the inbound and outbound communication paths for your agent. You can restrict access to only the resources explicitly required by your agent, such as storage accounts, databases, or APIs, while blocking all other traffic by default. This approach ensures that your agent operates within a tightly scoped network boundary, reducing the risk of data leakage or unauthorized access. By default, this setup simplifies security configuration while enforcing strong isolation guarantees, ensuring that each agent deployment remains secure, compliant, and aligned with enterprise networking policies.

---

## When to Use This Template

Use this template when you need:
- **Full end-to-end network isolation** — All resources behind private endpoints with no public internet access
- **BYO VNet control** — You manage your own virtual network, subnets, and network security groups
- **Standard agent setup with BYO resources** — Customer-managed Storage, Cosmos DB, and AI Search for data residency and compliance
- **System Assigned Managed Identity** — Simplified identity management with platform-managed credentials

### Template Decision Guide

Use the table below to choose the right infrastructure template for your scenario:

| Template | Agent Type | Networking | Identity | Key Use Case |
|----------|-----------|------------|----------|-------------|
| [**15** (this template)](../15-private-network-standard-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | E2E network isolation with full agent capabilities |
| [**19**](../19-private-network-agent-tools/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** tools behind VNet (MCP, OpenAPI, Functions, A2A) |
| [**17**](../17-private-network-standard-user-assigned-identity-agent-setup/) | Standard (BYO resources) | BYO VNet + Private Endpoints | **User Assigned MI** | Same as 15 but with user-managed identity |
| [**16**](../16-private-network-standard-agent-apim-setup-preview/) | Standard (BYO resources) | BYO VNet + Private Endpoints | System Assigned MI | Same as 15 **plus** private APIM integration (preview) |
| [**18**](../18-managed-virtual-network-preview/) | Standard (BYO resources) | **Managed VNet** (Microsoft-managed) | System Assigned MI | Network isolation without managing your own VNet (preview) |
| [**15a**](../15a-private-network-evaluation-only-setup/) | Evaluation only | BYO VNet + Private Endpoints | System Assigned MI | Minimal setup for evaluation — no Cosmos DB, AI Search, or capability host |
| [**11**](../11-private-network-basic-vnet/) | **Basic** (platform-managed) | BYO VNet injection | System Assigned MI | Basic agents with VNet isolation — no BYO resources needed |
| [**41**](../41-standard-agent-setup/) | Standard (BYO resources) | **Public** (no VNet) | System Assigned MI | Standard agents without network isolation |
| [**40**](../40-basic-agent-setup/) | **Basic** (platform-managed) | **Public** (no VNet) | System Assigned MI | Simplest setup — no BYO resources, no private networking |

---

## Deploy to Azure

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F15-private-network-standard-agent-setup%2Fazuredeploy.json)

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

2. Two subnets are needed as well:
    - **Agent Subnet** (e.g., 192.168.0.0/24): Hosts Agent client for Agent workloads, delegated to Microsoft.App/environments. The recommended size should be /24 for this delegated subnet.
    - **Private endpoint Subnet** (e.g. 192.168.1.0/24): Hosts private endpoints
    - Ensure that the address spaces for the used VNET does not overlap with any existing networks in your Azure environment or reserved IP ranges like the following: 169.254.0.0/16,172.30.0.0/16,172.31.0.0/16,192.0.2.0/24,0.0.0.0/8,127.0.0.0/8,100.100.0.0/17,100.100.192.0/19,100.100.224.0/19,100.64.0.0/11.
    This includes all address space(s) you have in your VNET if you have more than one, and peered VNETs.

  > **Notes:**
  - If you do not provide an existing virtual network, the template will create a new virtual network with the default address spaces and subnets described above. If you use an existing virtual network, make sure it already contains two subnets (Agent and Private Endpoint) before deploying the template.
  - The account-level capability host is created implicitly by the platform via `networkInjections.scenario='agent'` on the Foundry account (see `modules-network-secured/ai-account-identity.bicep`). Only one capability host per account is allowed, so `main.bicep` does not declare a second one for fresh deployments. Set `createAccountCapabilityHost=true` only when the account has no capability host — BYO accounts without one, or after running `deleteCapHost.sh` (see [Account Deletion Prerequisites and Cleanup Guidance](#account-deletion-prerequisites-and-cleanup-guidance)).
  - You must ensure the subnet is exclusively delegated to __Microsoft.App/environments__ and cannot be used by any other Azure resources.



### Limitations / Known Issues

1. The delegated agent subnet must be exclusively used by a single Foundry account. It cannot be shared across accounts.
2. The Foundry resource and the virtual network must be in the same Azure region. BYO resources (Storage, Cosmos DB, AI Search) may be in different regions.
3. For the virtual network IP range, you may use any Private Class A, B or C IP range. Private Class A IP address ranges (10.x.x.x) are only supported in the following regions: **Australia East, Brazil South, Canada East, East US, East US 2, France Central, Germany West Central, Italy North, Japan East, South Africa North, South Central US, South India, Spain Central, Sweden Central, UAE North, UK South, West US, West US 3.** Use Class B (172.16.x.x) or C (192.168.x.x) ranges for other regions. You may not use any other IP range that overlaps to the list above or uses public IP ranges.
4. This template does **not** support tools (MCP servers, OpenAPI tools, Azure Functions, A2A) behind the VNet. Use [template 19](../19-private-network-agent-tools/) for that scenario.
5. There is no upgrade path from BYO VNet (this template) to Managed Virtual Network (template 18). A Foundry resource redeployment is required.
6. All projects within the same Foundry account share model deployments. Per-project model isolation is not supported.
7. Cosmos DB is deployed as single-region. Multi-region replication must be configured manually post-deployment.
8. When reusing an existing Foundry account (`existingAiFoundryAccountResourceId`), the template will not create a new model deployment if `skipModelDeployment` is set to `true`. The required model deployment(s) must already exist on the BYO account.

### Account Deletion Prerequisites and Cleanup Guidance

Before deleting an **Account** resource, it is essential to first delete the associated **Account Capability Host**. Failure to do so may result in residual dependencies—such as subnets and other provisioned resources (e.g., ACA applications)—remaining linked to the capability host. This can lead to errors such as **"Subnet already in use"** when attempting to reuse the same subnet in a different account deployment.

**Cleanup Options**

**1. Full Account Removal**: To completely remove an account, you must delete and purge the account. Simply deleting the account is not sufficient, you must purge so that deletion of the associated capability host is triggered. The service will automatically handle the removal of the capability host and any linked resources in the background. To purge the account, use the following [link](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource). Please allow approximately max of 20 minutes for all resources to be fully unlinked from the account.

**2. Retain Account, Remove Capability Host**: If you intend to retain the account but remove the capability host, execute the script `deleteCapHost.sh` located in this folder. After deletion, allow approximately max of 20 minutes for all resources to be fully unlinked from the account. To recreate the capability host, redeploy `main.bicep` with `createAccountCapabilityHost=true`.

> **Note**: The capability host name to enter when prompted by `deleteCapHost.sh` follows the platform convention `<accountName>@aml_aiagentservice` for implicitly-created hosts. When `createAccountCapabilityHost=true` was used previously, the same conventional name applies (it is the module's default).


> **Important**: Before deleting the account capability host, ensure that the **project capability host** is deleted.

### Template Customization

Note: If not provided, the following resources will be created automatically for you:
- VNet and two subnets
- Azure Cosmos DB for NoSQL
- Azure AI Search
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
| `skipModelDeployment` | When `true`, skip creating a model deployment. Recommended when reusing an existing Foundry account that already has the required model deployments. | `false` | No |
| `vnetName` | Virtual Network name. When `existingVnetResourceId` is set, the name is derived from that resource ID and this parameter is ignored. When creating a new VNet, leave empty to use the generated default. | `''` | No |
| `agentSubnetName` | Subnet name for agent workloads | `agent-subnet` | No |
| `agentSubnetPrefix` | Address prefix for agent subnet | `192.168.0.0/24` | No |
| `peSubnetName` | Subnet name for private endpoints | `pe-subnet` | No |
| `peSubnetPrefix` | Address prefix for PE subnet | `192.168.1.0/24` | No |
| `existingVnetResourceId` | Full ARM Resource ID of an existing VNet | `''` (creates new) | No |
| `reuseExistingSubnets` | When `true` and `existingVnetResourceId` is set, the template will reference your existing subnets without modifying them. Use this when your subnets are already configured by your platform team (NSG, route tables, private endpoint network policies) and tenant policies forbid changes. | `false` | No |
| `vnetAddressPrefix` | Address space for new VNet | `192.168.0.0/16` | No |
| `aiSearchResourceId` | ARM Resource ID of existing AI Search | `''` (creates new) | No |
| `azureStorageAccountResourceId` | ARM Resource ID of existing Storage account | `''` (creates new) | No |
| `azureCosmosDBAccountResourceId` | ARM Resource ID of existing Cosmos DB | `''` (creates new) | No |
| `existingAiFoundryAccountResourceId` | Full ARM Resource ID of an existing Microsoft Foundry (Cognitive Services / AIServices) account to reuse. When set, the template will not create a new account. | `''` (creates new) | No |
| `assignContainerRoles` | When `true`, pre-assign the container-scoped data-plane roles (Storage Blob Data Owner / Cosmos Built-in Data Contributor on the agent containers). Leave `false`: the **implicit** project capability host provisions these containers and their role assignments during create. | `false` | No |
| `dnsZonesSubscriptionId` | Subscription ID for existing DNS zones. Accepts either a bare GUID (`<subscription-id>`) or a full ARM subscription path (`/subscriptions/<subscription-id>`); the template normalizes the value internally. | `''` (current sub) | No |
| `existingDnsZones` | Map of DNS zone names to resource groups | All empty (creates new) | No |
| `enableContainerRegistry` | When `true`, creates an Azure Container Registry (Premium SKU) with a private endpoint in the PE subnet, a `privatelink.azurecr.io` DNS zone, and an AcrPull role assignment for the project managed identity. | `true` | No |
| `createDependentResourcePrivateEndpoints` | When `true`, creates private endpoints and DNS zone groups for AI Search, Storage, and Cosmos DB. Set `false` only when the supplied existing resources already have private endpoints reachable from the selected VNet. The new Foundry account private endpoint is always created. | `true` | No |
| `assignProjectStorageAndCosmosAccountRoles` | Assigns Cosmos DB Operator and Storage Blob Data Contributor to the Project managed identity. Set `false` for caller-authorized `capabilitySettings` provisioning, then grant both roles to the Project identity before data-plane operations. | `true` | No |
| `developerIpCidr` | Developer IP CIDR to allowlist for ACR push access (e.g., `203.0.113.0/26`). When set, enables public network access with a deny-all default + an IP allowlist rule so developers can push images. When empty, public access remains fully disabled. | `''` | No |

When `assignProjectStorageAndCosmosAccountRoles=false`, grant **Cosmos DB Operator** on the supplied Cosmos DB account and **Storage Blob Data Contributor** on the supplied Storage account to the ARM deployment caller before creating the project. The Project managed identity should not hold those two account-level roles during `capabilitySettings` provisioning. Grant them to the Project managed identity only after provisioning succeeds and before the project performs data-plane operations.

#### BYO Resource Details

1. **Use Existing Virtual Network and Subnets**

To use an existing VNet and subnets, set the existingVnetResourceId parameter to the full Azure Resource ID of the target VNet and its address range, and provide the names of the two required subnets.  If the existing VNet is associated with private DNS zones, set the existingDnsZones parameter to the resource group name in which the zones are located. For example:
- param existingVnetResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>"
- param agentSubnetName string = 'agent-subnet' //optional, default is 'agent-subnet'
- param agentSubnetPrefix string = '192.168.0.0/24' //optional, default is '192.168.0.0/24'
- param peSubnetName string = 'pe-subnet' //optional, default is 'pe-subnet'
- param peSubnetPrefix string = '192.168.1.0/24' //optional, default is '192.168.1.0/24'
- param dnsZonesSubscriptionId string = '' //optional, leave empty to use current subscription, or set to a subscription ID if DNS zones are in a different subscription
- param existingDnsZones = {

         'privatelink.services.ai.azure.com': 'privzoneRG' //add resource group name where your private DNS zone is located

         'privatelink.openai.azure.com': '' //Leave empty to create new private dns zone... }

💡 If subnets information is provided then make sure it exist within the specified VNet to avoid deployment errors. If subnet information is not provided, the template will create subnets with the default address space.

💡 **Reuse pre-configured subnets**: If your subnets are already configured by your platform team (NSG, route tables, `privateEndpointNetworkPolicies` set per tenant policy), set `reuseExistingSubnets = true`. This tells the template to reference the subnets without re-applying their configuration, which prevents an inadvertent reset of subnet properties on redeploy.

⚠️ **One Foundry account per agent subnet**: You may reuse a VNet across Foundry accounts, but each network-injected account requires its own subnet delegated exclusively to `Microsoft.App/environments`. When creating a new account in an existing VNet, create a new delegated subnet and pass its name as `agentSubnetName`. The private endpoint subnet can be reused.

💡 **Reuse existing dependent resources and networking**: Supply `aiSearchResourceId`, `azureStorageAccountResourceId`, and `azureCosmosDBAccountResourceId`, point `existingVnetResourceId` at the shared VNet, set `reuseExistingSubnets = true`, and provide the existing private DNS zones. If those resources already have private endpoints reachable from the VNet, set `createDependentResourcePrivateEndpoints = false` to preserve them. The template still creates a private endpoint and DNS zone group for the new Foundry account.

💡 **Cross-Subscription DNS Zones**: All DNS zones specified in `existingDnsZones` will be referenced from the subscription specified in `dnsZonesSubscriptionId`. Leave this parameter empty (default) to use the current deployment subscription, or set it to a subscription ID if your DNS zones are located in a different subscription. The parameter accepts either a bare subscription GUID or a full ARM subscription path (`/subscriptions/<subscription-id>`); the template normalizes the value internally.

⚠️ **Important**: When `dnsZonesSubscriptionId` is set to a different subscription, ALL DNS zones in `existingDnsZones` must have resource groups specified (non-empty values). The template does not support creating new DNS zones in a different subscription. Empty resource groups are only allowed when creating zones in the current deployment subscription.


2. **Use an existing Azure Cosmos DB for NoSQL**

To use an existing Cosmos DB for NoSQL resource, set cosmosDBResourceId parameter to the full Azure Resource ID of the target Cosmos DB.
- param azureCosmosDBAccountResourceId string =  /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName}


3. **Use an existing Azure AI Search resource**

To use an existing Azure AI Search resource, set aiSearchServiceResourceId parameter to the full Azure resource Id of the target Azure AI Search resource.
 - param aiSearchResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Search/searchServices/{searchServiceName}

> **AAD auth is required on the existing service.** Foundry connects to Search with
> `authType=AAD`, so the service must accept Microsoft Entra (AAD) data-plane tokens
> (local auth disabled, or `authOptions` includes an `aadOrApiKey` block). A new
> Search service defaults to API-keys-only, which rejects AAD and makes agents fail
> with HTTP 403. When you bring an existing service, the template checks its live
> state and stops the deployment early with the exact fix command if it is
> API-keys-only. To enable AAD before deploying:
> ```bash
> az search service update --name <search-name> --resource-group <search-rg> \
>   --subscription <search-sub> --auth-options aadOrApiKey \
>   --aad-auth-failure-mode http401WithBearerChallenge
> ```

> **AI Search → AI Services connectivity**: This template configures AI Services with `networkAcls.bypass: AzureServices`, which allows Azure AI Search to reach AI Services through the trusted-services bypass. This works for most scenarios. If your security policy requires removing the bypass (setting it to `None`), deploy [Shared Private Links](../deployment-tools/networking/README.md) from AI Search to AI Services instead — this creates a private endpoint from AI Search's managed infrastructure directly into AI Services via Private Link.


4. **Use an existing Azure Storage account**

To use an existing Azure Storage account, set aiStorageAccountResourceId parameter to the full Azure resource Id of the target Azure Storage account resource.
- param aiStorageAccountResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}


5. **Use an existing Microsoft Foundry account**

To reuse an existing Microsoft Foundry (Cognitive Services / AIServices kind) account instead of creating a new one, set `existingAiFoundryAccountResourceId` to the full Azure Resource ID of the target account. The template will reference the existing account (cross-RG / cross-subscription aware) and skip the deterministic-suffix account creation path (which would otherwise create a new account on every redeploy).

- param existingAiFoundryAccountResourceId string = '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.CognitiveServices/accounts/{accountName}'
- param skipModelDeployment bool = true  // recommended when the BYO account already has the required model deployment(s)
- param createAccountCapabilityHost bool = false  // set true ONLY if the BYO account has no capability host yet

💡 **When to use this**: bring-your-own-account is intended for scenarios where the Foundry account is provisioned ahead of time by a platform team or landing zone, and the workload deployment must reuse it (for compliance, naming standards, or to avoid orphaned accounts on retry).

⚠️ **Important**: When `existingAiFoundryAccountResourceId` is set, the required model deployment(s) must already exist on the BYO account if `skipModelDeployment = true`. The agent service depends on at least one model deployment matching `modelName` / `modelVersion` to function.

⚠️ **Capability host on BYO accounts**: If your BYO account already has a capability host (one created via `networkInjections.scenario='agent'` at account creation, or a previous explicit creation), leave `createAccountCapabilityHost=false`. Set it to `true` only when the account has no capability host — only one capability host per account is allowed and a second create will fail.

---

## Deploy the bicep template

Choose your deployment method: Use the "Deploy to Azure" button from the provided README for an guided experience in Azure Portal

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
  - Data is isolated between projects. Agents in one project cannot access resources from another. Projects are currently the unit of  sharing and isolation in Foundry. See the what is AI foundry article for more information on Foundry projects.

**Bring Your Own (BYO) Azure Resources**: ensures all sensitive data remains under customer control. All agents created using our service are stateful, meaning they retain information across interactions. With this setup, agent states are automatically stored in customer-managed, single-tenant resources. The required Bring Your Own Resources include:
- BYO File Storage: All files uploaded by developers (during agent configuration) or end-users (during interactions) are stored directly in the customer’s Azure Storage account.
- BYO Search: All vector stores created by the agent leverage the customer’s Azure AI Search resource.
- BYO Thread Storage: All customer messages and conversation history will be stored in the customer’s own Azure Cosmos DB account.

By bundling these BYO features (file storage, search, and thread storage), the standard setup guarantees that your deployment is secure by default. All data processed by Microsoft Foundry Agent Service is automatically stored at rest in your own Azure resources, helping you meet internal policies, compliance requirements, and enterprise security standards.

### Azure Resources Created

Microsoft Foundry (Cognitive Services)
- Type: Microsoft.CognitiveServices/accounts
- API version: 2026-05-15-preview
- Kind: AIServices
- SKU: S0
- Identity: System-assigned
- Features:
  - Custom subdomain name
  - Disabled public network access
  - Network ACLs with Azure Services bypass

AI Model Deployment
- Type: Microsoft.CognitiveServices/accounts/deployments
- API version: 2026-05-15-preview
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
This implementation utilizes a BYO VNet (Bring Your Own Virtual Network) approach, also known as custom VNet support with subnet delegation. Within your existing virtual network, one delegated subnet will be created.

Network Security
- Public network access disabled
- Private endpoints for all services
- Network ACLs with deny by default

**Network Infrastructure**
- A Virtual Network (192.168.0.0/16) is created (if existing isn't passed in)
- Agent Subnet (192.168.0.0/24): Hosts Agent client
- Private endpoint Subnet (192.168.1.0/24): Hosts private endpoints

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

## Module Structure

```text
modules-network-secured/
├── ai-account-identity.bicep                       # Microsoft Foundry deployment and configuration (supports BYO existing account). Account caphost is implicit via networkInjections.scenario='agent'
├── ai-project-identity.bicep                       # Foundry project + connections. Sets capabilitySettings so the project capability host is created implicitly
├── ai-project-identity-unique.bicep                # add-project.bicep variant (unique connection names) — also sets capabilitySettings
├── ai-existing-project-connections.bicep           # add-existing-project.bicep variant — upserts the existing project with capabilitySettings
├── ai-search-role-assignments.bicep                # AI Search RBAC configuration
├── application-insights.bicep                      # Workspace-based Application Insights for agent tracing
├── azure-storage-account-role-assignments.bicep    # Storage Account RBAC configuration
├── blob-storage-container-role-assignments.bicep   # Blob Storage Container RBAC configuration (off by default; implicit caphost provisions containers)
├── cosmos-container-role-assignments.bicep         # CosmosDB container Account RBAC configuration (off by default; implicit caphost provisions containers)
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

> **Scenario 22 note:** `add-account-capability-host.bicep` and `add-project-capability-host.bicep` from template 15 are intentionally **absent** — both capability hosts are implicit (account via `networkInjections`, project via `capabilitySettings`).

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
# (Optional) Adding Multiple Projects to Foundry Deployment

This guide explains how to add additional projects to your existing AI Foundry deployment with network security and capability hosts.

## Overview

After deploying your initial AI Foundry setup using `main.bicep`, you can add additional projects using the modular approach provided in this repository. Each new project will:

- ✅ **Reuse existing shared infrastructure** (AI Services account, Storage, Cosmos DB, AI Search, VNet)
- ✅ **Create independent projects** with unique identities and connections
- ✅ **Set up proper role assignments** and capability hosts for each project
- ✅ **Maintain network security** configurations from your original deployment
- ✅ **Deploy independently** without affecting existing projects

## Files Added

### Core Deployment Files

| File | Purpose |
|------|---------|
| `add-project.bicep` | Main Bicep template for adding new projects |
| `add-project.bicepparam` | Parameters file template for new projects |
| `modules-network-secured/ai-project-identity-unique.bicep` | Modified project module with unique connection names |
| `modules-network-secured/blob-storage-container-role-assignments-unique.bicep` | Modified storage role assignment module |

### Helper Files

| File | Purpose |
|------|---------|
| `get-existing-resources.ps1` | PowerShell script to discover existing resource names |

## Prerequisites

1. ✅ **Existing AI Foundry deployment** completed using `main.bicep`
2. ✅ **Azure CLI** installed and logged in
3. ✅ **Proper permissions** on the resource group and existing resources
4. ✅ **Resource names** from your existing deployment

## Step-by-Step Guide

### Step 1: Discover Existing Resource Names

Run the PowerShell script to automatically discover your existing resource names:

```powershell
# Navigate to your repository folder
cd "path\to\your\AgentRepro\folder"

# Run the discovery script
.\get-existing-resources.ps1 -ResourceGroupName "your-resource-group-name"

# Optional: Include subscription ID if needed
.\get-existing-resources.ps1 -ResourceGroupName "your-resource-group-name" -SubscriptionId "your-subscription-id"
```

**Example output:**
```
=== Summary for add-project.bicepparam ===
param existingAccountName = 'aiservicesytlz'
param existingAiSearchName = 'aiservicesytlzsearch'
param existingStorageName = 'aiservicesytlzstorage'
param existingCosmosDBName = 'aiservicesytlzcosmosdb'
param accountResourceGroupName = 'agenticvnet'
param aiSearchResourceGroupName = 'agenticvnet'
param storageResourceGroupName = 'agenticvnet'
param cosmosDBResourceGroupName = 'agenticvnet'
```

### Step 2: Configure Parameters File

Copy the output from Step 1 and update your `add-project.bicepparam` file:

### Step 3: Deploy the New Project

Deploy using Azure CLI:

```powershell
az deployment group create `
  --resource-group "your-resource-group" `
  --template-file "add-project.bicep" `
  --parameters "add-project.bicepparam"
```

## Adding Multiple Projects

To add additional projects, repeat the process with different parameter values:

### For a Third Project:

1. **Update project-specific parameters:**
   ```bicep
   param projectName = 'thirdproject'  // Must be unique
   param displayName = 'Third Project'
   ```

3. **Deploy using the new parameters file:**
   ```powershell
   az deployment group create `
     --resource-group "your-resource-group" `
     --template-file "add-project.bicep" `
     --parameters "add-project.bicepparam"
   ```

## What Gets Created

Each new project deployment creates:

| Resource | Description |
|----------|-------------|
| **AI Foundry Project** | New project under your existing AI Services account |
| **Managed Identity** | Project-specific system-assigned identity |
| **Unique Connections** | Project-specific connections to shared resources |
| **Capability Host** | Created **implicitly** by AccountRP from the project's `capabilitySettings` |
| **RBAC Assignments** | Proper permissions on shared resources |

### Role Assignments Created:

- ✅ **Storage Blob Data Contributor** on Storage Account
- ✅ **Storage Blob Data Owner** on project-specific containers
- ✅ **Cosmos DB Operator** on Cosmos DB Account
- ✅ **Cosmos Built-In Data Contributor** on project-specific containers
- ✅ **Search Index Data Contributor** on AI Search Service
- ✅ **Search Service Contributor** on AI Search Service

## Configuration Reference

### Required Parameters (Must Customize for Each Project)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `projectName` | Unique name for the project | `'secondproject'` |
| `displayName` | Display name in Azure portal | `'Second Project'` |
| `projectDescription` | Description of the project | `'My second AI project'` |

### Existing Resource Parameters (From Script)

| Parameter | Description | Source |
|-----------|-------------|---------|
| `existingAccountName` | AI Services account name | Output from `get-existing-resources.ps1` |
| `existingAiSearchName` | AI Search service name | Output from `get-existing-resources.ps1` |
| `existingStorageName` | Storage account name | Output from `get-existing-resources.ps1` |
| `existingCosmosDBName` | Cosmos DB account name | Output from `get-existing-resources.ps1` |
| `*ResourceGroupName` | Resource group names | Usually same as deployment RG |
| `*SubscriptionId` | Subscription IDs | Usually same subscription |


## Security Considerations

- ✅ **Least Privilege**: Each project gets only the permissions it needs
- ✅ **Isolated Containers**: Projects get separate storage containers
- ✅ **Network Security**: Inherits network security from original deployment
- ✅ **Unique Identities**: Each project has its own managed identity

## Limitations

- 📝 All projects share the same model deployments
- 📝 Projects must be in the same region as the original deployment
- 📝 Network configuration is inherited from original deployment

## References

- [Microsoft Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Microsoft Foundry RBAC Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)

# (Optional) Securing an Existing Project (Reuse In-Place)

`add-project.bicep` always creates a brand new project and appends a short random
suffix to keep the name unique. That is the right behavior when you want a fresh
project, but it does not help when you already have a Foundry project in use and
simply want to wire the network-secured agent setup onto it.

`add-existing-project.bicep` covers that case. It reuses the project you name, in
place, with no new project and no suffix. This is the common situation when you
are securing an already-running Foundry deployment behind private endpoints and
do not want to recreate projects or move agents.

## When to use which

| Goal | Template |
|------|----------|
| Add a new, separate project to an existing Foundry account | `add-project.bicep` |
| Wire/secure the agent setup onto a project that already exists | `add-existing-project.bicep` |

## What it does

`add-existing-project.bicep` references the existing project with the `existing`
keyword and then layers on the same building blocks the new-project flow uses:

- ✅ **Adds the three agent connections** (Cosmos DB, Storage, AI Search) to the
  existing project using AAD (Entra ID) auth, no keys.
- ✅ **Assigns the required RBAC roles** to the project managed identity on the
  shared Storage, Cosmos DB, and AI Search resources.
- ✅ **Creates (or updates) the project capability host** bound to those exact
  connection names.
- ✅ **Assigns the container-scoped roles** for the project's storage and Cosmos
  containers after the capability host exists.
- ✅ **Reuses every shared module** from the new-project flow, so behavior stays
  consistent between the two paths.

It does **not** create the project, change its display name, or touch its
description. Those stay exactly as they are.

## Prerequisites

1. ✅ **The project already exists** under the target AI Services (Foundry)
   account, and the account is the network-secured account from your original
   deployment.
2. ✅ **The project has a system-assigned managed identity.** The connections and
   role assignments target that identity.
3. ✅ **Account-level network injection is already in place** (the agent subnet is
   configured on the account capability host from the original `main.bicep`
   deployment). Network security is account-scoped, so once the account is
   injected, every project under it inherits agent-subnet security. You do not
   re-run the full template per project.
4. ✅ **AI Search allows AAD auth.** Foundry connects to Search with `authType=AAD`,
   so the service must accept Microsoft Entra (AAD) data-plane tokens. A service is
   ready when local auth is disabled (RBAC-only) or its `authOptions` includes an
   `aadOrApiKey` block. The Azure default for a new Search service is API-keys-only,
   which rejects AAD and makes agents fail with HTTP 403. This template now checks
   the live state and stops the deployment early with the exact fix command if the
   service is API-keys-only, so you will not get a silent broken connection. To
   enable AAD up front:
   ```bash
   az search service update --name <search-name> --resource-group <search-rg> \
     --subscription <search-sub> --auth-options aadOrApiKey \
     --aad-auth-failure-mode http401WithBearerChallenge
   ```
5. ✅ **Run the deployment in the account's resource group.** Like
   `add-project.bicep`, this template operates on the project and capability host
   at the deployment resource group, so deploy into the resource group that holds
   the Foundry account. The shared Storage, Cosmos DB, and AI Search resources can
   live in other resource groups or subscriptions (set their RG and subscription
   parameters accordingly).
6. ✅ **Azure CLI** installed and logged in, with permission to create role
   assignments and capability hosts on the target resources.
7. ✅ **Cross-subscription resources stay in the same tenant.** If your Storage,
   Cosmos DB, or AI Search resources live in other subscriptions, they must be
   reachable by the deployment identity and in the same Microsoft Entra tenant as
   the project managed identity, so the AAD connections and role assignments
   resolve.

## Step-by-step

### Step 1: Configure the parameters file

Edit `add-existing-project.bicepparam` and set `projectName` to the existing
project, plus the names, resource groups, and subscription IDs of the shared
resources from your original deployment. You can reuse `get-existing-resources.ps1`
to discover the shared resource names.

```bicep
// EXISTING project to reuse in place (no suffix is appended)
param projectName = 'your-existing-project-name'
// Scenario 22: capabilitySettings is applied via a project upsert, so pass the
// project's CURRENT region and display name so nothing is changed.
param location = 'your-project-region'
param displayName = 'your-existing-project-display-name'

param existingAccountName = 'your-foundry-account'
param accountResourceGroupName = 'your-resource-group'
param accountSubscriptionId = 'your-subscription-id'
// ... plus existingAiSearchName / existingStorageName / existingCosmosDBName
//     and their resource groups and subscription IDs
```

### Step 2: Preview the change

Run a what-if first so you can see exactly what will be added before anything is
deployed:

```powershell
az deployment group what-if `
  --resource-group "your-resource-group" `
  --template-file "add-existing-project.bicep" `
  --parameters "add-existing-project.bicepparam"
```

### Step 3: Deploy

```powershell
az deployment group create `
  --resource-group "your-resource-group" `
  --template-file "add-existing-project.bicep" `
  --parameters "add-existing-project.bicepparam"
```

## Handling already-configured projects

Production projects are rarely a blank slate. The template has a few optional
parameters so you can point it at a project that already has some of this wiring
in place. Review the project's current connections, capability host, and role
assignments before you run, then set these as needed:

- **`assignRoles`** (default `true`). Set to `false` to skip every
  role-assignment module. Use this when the project identity is already
  permissioned on Storage, Cosmos DB, and AI Search. Manual or earlier
  assignments use different assignment names, and Azure rejects a duplicate on
  the same identity, role, and scope with `RoleAssignmentExists`. Skipping the
  modules avoids that conflict. Do not set `assignRoles = false` unless every
  role in the checklist below already exists for the project managed identity.
  When a required role is missing, the deployment still succeeds, but the agent
  fails at runtime rather than at deploy time, which is harder to diagnose.
- **`cosmosDBConnectionName` / `azureStorageConnectionName` /
  `aiSearchConnectionName`** (default empty). Leave empty to use the
  deterministic default `<resourceName>-<project>`. Set them to the exact
  connection names a pre-existing capability host already binds to, so the
  capability host keeps pointing at the same connections. Note that if a
  connection with the supplied (or default) name already exists, this deployment
  updates that connection to target the Storage, Cosmos DB, and AI Search
  resources you pass in. Do not reuse a live connection name unless it already
  targets the resources you intend.
- **`location` / `displayName`** (scenario 22, required). capabilitySettings is
  applied via a project upsert, so pass the project's CURRENT region and display
  name to avoid changing them. The project capability host is then created
  **implicitly** by AccountRP from those capabilitySettings — there is no
  `projectCapHost` name to set.

### Required roles when you skip role assignment

If you set `assignRoles = false`, confirm the project managed identity already
holds these roles before you run, or the agent will fail at runtime:

| Resource | Role | Scope |
|----------|------|-------|
| Storage account | Storage Blob Data Contributor | Storage account |
| Storage account | Storage Blob Data Owner (ABAC-conditioned to `*-azureml-agent` containers) | Storage account |
| Cosmos DB account | Cosmos DB Operator | Cosmos DB account |
| Cosmos DB data plane | Cosmos DB Built-in Data Contributor | `enterprise_memory` database |
| AI Search | Search Index Data Contributor | AI Search service |
| AI Search | Search Service Contributor | AI Search service |

## Idempotency

The template is safe to re-run. Connection names and role-assignment IDs are
derived deterministically from the project name, so a second run converges on the
same resources instead of creating duplicates.

## Scope and caveats

This template targets the retrofit case: wiring the agent setup onto a project
that already exists. Keep these points in mind:

- 📝 A deployment that fails partway can leave the project partly wired (some
  connections or roles present, the capability host not yet created). Re-running
  after you fix the cause converges the rest, because every step is
  deterministic and idempotent.
- 📝 The three connections are created (or updated) with names derived from the
  shared resource names plus the project name, unless you override them. If the
  project already has connections created another way (for example through the
  portal, which sanitizes and suffixes names), pass the override parameters so
  the capability host binds to the names that already exist instead of adding new
  ones.
- 📝 The project capability host is created **implicitly** by AccountRP from the
  project's `capabilitySettings`. There is no explicit capability-host resource
  or `projectCapHost` name in this scenario.
- 📝 Network injection is account-scoped, not project-scoped. Once the account
  capability host has the agent subnet (from the original `main.bicep`
  deployment), every project under that account inherits agent-subnet security.
  You run this lighter template per project, not the full setup.
