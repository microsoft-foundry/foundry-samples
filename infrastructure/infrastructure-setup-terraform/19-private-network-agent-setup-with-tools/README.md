---
description: This set of templates demonstrates how to set up Azure AI Agent Service with virtual network isolation, private network links, and tools behind VNet.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent-tools-terraform
languages:
- hcl
---

# Microsoft Foundry: Standard Agent Setup with E2E Network Isolation (Terraform)

> **NEW**
> For support on deploying the right network isolation template, check out the [GitHub Copilot for Azure skill for private networking](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/resource/private-network/private-network.md) set-up!

---

## Overview

This Terraform implementation deploys a network-secured Microsoft Foundry agent environment with private networking, role-based access control (RBAC), and support for tools behind the VNet (MCP servers, OpenAPI tools, Azure Functions, A2A).

Standard setup supports private network isolation through utilizing **Bring Your Own Virtual Network (BYO VNet)** approach, also known as **custom VNet support with subnet delegation.**

This implementation gives you full control over the inbound and outbound communication paths for your agent. You can restrict access to only the resources explicitly required by your agent, such as storage accounts, databases, or APIs, while blocking all other traffic by default. This approach ensures that your agent operates within a tightly scoped network boundary, reducing the risk of data leakage or unauthorized access.

By default, the Foundry resource has **public network access disabled**.

This is the Terraform equivalent of [Bicep template 19](../../infrastructure-setup-bicep/19-private-network-agent-tools/).

### When to Use This Template

Use this template when you need:
- **Full end-to-end network isolation** — All resources behind private endpoints with no public internet access
- **BYO VNet control** — You manage your own virtual network, subnets, and network security groups
- **Standard agent setup with BYO resources** — Customer-managed Storage, Cosmos DB, and AI Search for data residency and compliance
- **Tools behind VNet** — MCP servers, OpenAPI tools, Azure Functions, or A2A agents deployed on the private VNet (requires separate tool deployment — see [MCP Server Deployment](#mcp-server-deployment))
- **System Assigned Managed Identity** — Simplified identity management with platform-managed credentials

### IP Range Support

> Use only supported RFC 1918 or RFC 6598 address space. For RFC 1918, use addresses within `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`. For RFC 6598 (CGNAT), use addresses within `100.64.0.0/10`, excluding `100.100.0.0/17`, `100.100.192.0/19`, and `100.100.224.0/19`. Public IP ranges aren't supported.

---

## Architecture

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

---

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
   - **Foundry Account Owner**: Needed to create the Microsoft Foundry account and project
   - **Owner or Role Based Access Administrator**: Needed to assign RBAC on the Azure resources used by this template
   - **Foundry User**: Needed to create and use agents, projects, or evaluation workloads after deployment

2. **Register Resource Providers**

   Make sure your subscription allows registering resource providers. Subnet delegation requires `Microsoft.App` to be registered.

   ```bash
   az provider register --namespace 'Microsoft.KeyVault'
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Storage'
   az provider register --namespace 'Microsoft.Search'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.App'
   az provider register --namespace 'Microsoft.ContainerService'
   ```

3. **Network administrator permissions** (if operating in a restricted or enterprise environment)

4. **Sufficient quota** for all resources in your target Azure region, including model deployment quota. If no BYO resources are provided, this template creates a Foundry resource, project, Cosmos DB, AI Search, and Storage account.

5. **Azure CLI** installed and configured

6. **Terraform CLI** v1.10.0 or later. This template uses the AzureRM and AzAPI providers.

---

## Pre-Deployment Steps

### Networking Requirements

1. Review network requirements and plan Virtual Network address space (default: `192.168.0.0/16`).

2. Three subnets are needed:

   | Subnet | Default CIDR | Purpose | Delegation |
   |--------|-------------|---------|------------|
   | `agent-subnet` | `192.168.0.0/24` | Agent compute (capability host). Recommended size: /24 | `Microsoft.App/environments` |
   | `pe-subnet` | `192.168.1.0/24` | Private endpoints for Storage, Cosmos DB, AI Search, AI Foundry | None |
   | `mcp-subnet` | `192.168.2.0/24` | MCP servers, OpenAPI tools, Azure Functions, A2A agents | `Microsoft.App/environments` |

3. Ensure the VNet address space does not overlap with:
   - Existing networks in your Azure environment
   - Reserved IP ranges: `169.254.0.0/16`, `172.30.0.0/16`, `172.31.0.0/16`, `192.0.2.0/24`, `0.0.0.0/8`, `127.0.0.0/8`, `100.100.0.0/17`, `100.100.192.0/19`, `100.100.224.0/19`
   - Peered VNets or on-premises address spaces

> **Notes:**
> - If you do not provide an existing VNet, the template creates a new one with the default address spaces above.
> - The agent subnet must be exclusively delegated to `Microsoft.App/environments` and cannot be used by any other Azure resources.

---

## Variables

### Required

| Variable | Description |
|----------|-------------|
| `location` | Azure region for all resources (see [IP Range Support](#ip-range-support)) |

### Optional — Resource Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ai_services_name_prefix` | `aifoundry` | Prefix for AI Foundry account name (a random suffix is appended) |
| `project_name` | `agent-project` | Name of the Foundry project |
| `vnet_address_space` | `["192.168.0.0/16"]` | VNet address space (only used when creating a new VNet) |
| `model_name` | `gpt-4.1` | Model to deploy |
| `model_version` | `2025-04-14` | Model version |
| `model_capacity` | `40` | Model deployment capacity (TPM) |
| `enable_container_registry` | `false` | Enable Azure Container Registry with Private Endpoint for hosted agent containers |
| `developer_ip_cidr` | `""` | Developer IP CIDR to allowlist for ACR push access (only used when ACR is enabled) |

### Optional — BYO (Bring Your Own) Resources

Leave empty to create new resources. Provide resource IDs to reuse existing ones.

| Variable | Default | Description |
|----------|---------|-------------|
| `existing_resource_group_name` | `""` | Name of an existing resource group |
| `existing_vnet_id` | `""` | Resource ID of an existing VNet (requires all 3 subnet IDs) |
| `existing_agent_subnet_id` | `""` | Resource ID of an existing agent subnet (delegated to `Microsoft.App/environments`) |
| `existing_pe_subnet_id` | `""` | Resource ID of an existing private endpoint subnet |
| `existing_mcp_subnet_id` | `""` | Resource ID of an existing MCP subnet (delegated to `Microsoft.App/environments`) |
| `existing_storage_account_id` | `""` | Resource ID of an existing Storage Account |
| `existing_cosmosdb_account_id` | `""` | Resource ID of an existing Cosmos DB account |
| `existing_ai_search_id` | `""` | Resource ID of an existing AI Search service |
| `existing_dns_zones_resource_group` | `""` | Resource group containing existing private DNS zones (all 6 zones expected) |
| `existing_dns_zones_subscription_id` | `""` | Subscription ID for DNS zones (only used with `existing_dns_zones_resource_group`) |
| `existing_fabric_workspace_id` | `""` | Resource ID of an existing Fabric workspace for Data Agent PE |

See `code/example.tfvars` for a complete configuration reference with all variables.

---

## Deploy

### 1. Set subscription

```bash
# Linux/macOS
export ARM_SUBSCRIPTION_ID="YOUR_SUBSCRIPTION_ID"

# Windows PowerShell
$env:ARM_SUBSCRIPTION_ID = "YOUR_SUBSCRIPTION_ID"

# Windows cmd
set ARM_SUBSCRIPTION_ID=YOUR_SUBSCRIPTION_ID
```

### 2. Log in to Azure

```bash
az login
```

### 3. Initialize Terraform

```bash
cd infrastructure/infrastructure-setup-terraform/19-private-network-agent-setup-with-tools/code
terraform init
```

### 4. Configure variables

Copy the example variables file and set your target region:

```bash
cp example.tfvars terraform.tfvars
```

Edit `terraform.tfvars` — at minimum, set `location` to your target region. For BYO resources, fill in the resource IDs for the existing resources you want to reuse.

### 5. Plan and apply

```bash
terraform plan -var-file="terraform.tfvars" -out=tfplan
terraform apply "tfplan"
```

Deployment takes approximately **15–25 minutes**. The main time-consuming resources are the capability host provisioning and private endpoint creation.

### Verify Deployment

```bash
# Check Terraform outputs
terraform output

# List private endpoints (should see Storage, Cosmos DB, AI Search, AI Foundry)
az network private-endpoint list \
  --resource-group $(terraform output -raw resource_group_name) \
  --output table
```

After connecting to the VNet (via VPN or other method), verify DNS resolution:

```bash
nslookup <account-name>.services.ai.azure.com
nslookup <cosmos-account>.documents.azure.com
nslookup <storage-account>.blob.core.windows.net
```

Each should resolve to a private IP in your VNet range (e.g., `192.168.1.x`).

---

## What Gets Deployed

The template creates the following resources:

| Resource | Type | Key Configuration |
|----------|------|-------------------|
| Resource Group | `azurerm_resource_group` | `rg-aifoundry<random>` |
| Virtual Network | `azurerm_virtual_network` | 3 subnets (agent, PE, MCP), serialized to avoid locking |
| Storage Account | `azurerm_storage_account` | StorageV2, ZRS, public access disabled, SharedKey disabled |
| Cosmos DB | `azapi_resource` | NoSQL, serverless, public access disabled, local auth disabled |
| AI Search | `azapi_resource` | Standard SKU, public access disabled, AAD auth |
| AI Foundry Account | `azapi_resource` | `networkInjections` for agent + MCP subnets, public access disabled |
| Model Deployment | `azapi_resource` | Configurable model (default: gpt-4.1) |
| Private DNS Zones (6) | `azurerm_private_dns_zone` | Linked to VNet |
| Private Endpoints (4) | `azurerm_private_endpoint` | Storage, Cosmos DB, AI Search, AI Foundry (serialized) |
| Foundry Project | `azapi_resource` | System-assigned managed identity |
| Connections (3) | `azapi_resource` | Cosmos DB, Storage, AI Search (AAD auth) |
| RBAC Assignments (6) | `azapi_resource` | Phase A (before caphost) + Phase B (after caphost) |
| Capability Hosts (2) | `azapi_resource` | Account + Project |
| ACR (optional) | `azurerm_container_registry` | Premium SKU, PE + DNS zone, AcrPull role on project MI |
| Account Purger | `terraform_data` | Purges soft-deleted account on destroy |

When using BYO resources, any resource with a matching `existing_*` variable is skipped (not created). Data sources reference the existing resource instead. All downstream references (private endpoints, connections, RBAC) work identically.

### Authentication & Authorization

This template uses **System Assigned Managed Identity** with the following role assignments on the **Project Managed Identity**:

| Role | Resource | Phase |
|------|----------|-------|
| Search Index Data Contributor | AI Search | A (before caphost) |
| Search Service Contributor | AI Search | A |
| Storage Blob Data Contributor | Storage Account | A |
| Cosmos DB Operator | Cosmos DB Account | A |
| Cosmos DB SQL Built-in Data Contributor | Cosmos DB Account | B (after caphost) |
| Storage Blob Data Owner (with ABAC condition) | Storage Account | B |

### BYO Resources

All agents created using this service are **stateful** — they retain information across interactions. With the standard setup, agent state is stored in customer-managed, single-tenant resources:

- **BYO File Storage**: Files uploaded by developers or end-users are stored in the customer's Azure Storage account
- **BYO Search**: Vector stores created by the agent use the customer's Azure AI Search resource
- **BYO Thread Storage**: Messages and conversation history are stored in the customer's Azure Cosmos DB account

---

## BYO (Bring Your Own) Deployment Scenarios

This template supports mixing new and existing resources. Common scenarios:

### Scenario 1: Create Everything (default)

Set only `location`. All resources are created fresh:

```hcl
location = "swedencentral"
```

### Scenario 2: BYO Resource Group

Deploy into an existing resource group:

```hcl
location                     = "swedencentral"
existing_resource_group_name = "my-existing-rg"
```

### Scenario 3: BYO Networking + Backend Services

Reuse an existing VNet and backend resources (e.g., from a previous deployment):

```hcl
location                     = "swedencentral"
existing_resource_group_name = "my-existing-rg"
existing_vnet_id             = "/subscriptions/.../virtualNetworks/my-vnet"
existing_agent_subnet_id     = "/subscriptions/.../subnets/agent-subnet"
existing_pe_subnet_id        = "/subscriptions/.../subnets/pe-subnet"
existing_mcp_subnet_id       = "/subscriptions/.../subnets/mcp-subnet"
existing_storage_account_id  = "/subscriptions/.../storageAccounts/mystorage"
existing_cosmosdb_account_id = "/subscriptions/.../databaseAccounts/mycosmosdb"
existing_ai_search_id        = "/subscriptions/.../searchServices/mysearch"
existing_dns_zones_resource_group = "my-dns-rg"
```

### BYO Requirements

- **VNet**: All 3 subnet IDs must be provided together. Agent and MCP subnets must be delegated to `Microsoft.App/environments`.
- **Agent subnet**: Must not have an existing Service Association Link (SAL) from another Foundry account. One account per agent subnet.
- **Backend services**: Must have public access disabled.
- **DNS zones**: All 6 private DNS zones must exist in the specified resource group and be linked to the VNet.
- **DNS zone cross-subscription**: Set `existing_dns_zones_subscription_id` if the DNS zones are in a different subscription. The deployment identity needs `Private DNS Zone Contributor` on each referenced zone.

> **Cosmos DB Connection Note**: The Cosmos DB connection uses `authType: AAD` and includes the `ResourceId` in metadata. This is the only supported authentication type for the Cosmos DB connection used by the Agent Service.

---

## Connecting to a Private Foundry Resource

When public network access is disabled (the default), you need a secure connection to reach the Foundry resource. Azure provides three methods:

1. **Azure VPN Gateway** — Connect from your local network to the Azure VNet over an encrypted tunnel
2. **Azure ExpressRoute** — Use a private, dedicated connection from your on-premises infrastructure to Azure
3. **Azure Bastion** — Use a jump box VM on the VNet, accessed securely through the Azure portal

For detailed setup instructions, see: [Securely connect to Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?view=foundry#securely-connect-to-foundry).

## MCP Server Deployment

To deploy MCP servers on the private VNet after the base infrastructure is deployed:

```bash
# Create Container Apps environment on mcp-subnet
az containerapp env create \
  --resource-group <rg-name> \
  --name "mcp-env" \
  --location <location> \
  --infrastructure-subnet-resource-id <mcp-subnet-resource-id> \
  --internal-only true

# Deploy MCP server
az containerapp create \
  --resource-group <rg-name> \
  --name "my-mcp-server" \
  --environment "mcp-env" \
  --image <your-mcp-image> \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1
```

Then configure a private DNS zone for Container Apps. See the [Bicep 19 TESTING-GUIDE.md](../../infrastructure-setup-bicep/19-private-network-agent-tools/tests/TESTING-GUIDE.md) for details on DNS configuration for tools behind VNet.

---

## Teardown

### Account Deletion Prerequisites

Before deleting an Account resource, the associated capability hosts must be removed first. The `terraform destroy` command handles this automatically via dependency ordering and the account purger resource.

If you need to manually clean up:
1. Delete the **project capability host** first
2. Delete the **account capability host**
3. Delete and [**purge**](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource) the Foundry account
4. Allow approximately **20 minutes** for all resources to be fully unlinked

> **Important**: Simply deleting the account is not sufficient — you must also purge it so that the associated capability host deletion is triggered. The service will automatically handle the removal of the capability host and any linked resources in the background.

---

## Limitations / Known Issues

1. The delegated agent subnet must be exclusively used by a single Foundry account. It cannot be shared across accounts. A **Service Association Link (SAL)** is placed on the subnet during account creation. The SAL has `allowDelete: false` and may take up to 30 minutes to be released after the account is deleted and purged.
2. The Foundry resource and the VNet must be in the same Azure region. BYO backend resources (Storage, Cosmos DB, AI Search) may be in different regions.
3. Use only supported RFC 1918 or RFC 6598 address space. For RFC 1918, use addresses within `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`. For RFC 6598 (CGNAT), use addresses within `100.64.0.0/10`, excluding `100.100.0.0/17`, `100.100.192.0/19`, and `100.100.224.0/19`. Public IP ranges aren't supported.
4. All projects within the same Foundry account share model deployments. Per-project model isolation is not supported.
5. Cosmos DB is deployed as single-region. Multi-region replication must be configured manually post-deployment.
6. When using BYO resources, private endpoints are still created by this template. A random suffix is added to avoid naming collisions with existing private endpoints.

---

## File Structure

```
19-private-network-agent-setup-with-tools/
├── README.md              # This file
└── code/
    ├── main.tf            # All resources (networking, compute, RBAC, connections)
    ├── variables.tf       # Input variable definitions
    ├── locals.tf          # Computed locals (BYO flags, unified references)
    ├── data.tf            # Data sources (client config, existing resources)
    ├── outputs.tf         # Output values
    ├── providers.tf       # Provider configuration
    ├── versions.tf        # Provider version constraints
    └── example.tfvars     # Example variable values (copy to terraform.tfvars)
```

---

## Reference

- [Bicep template 19](../../infrastructure-setup-bicep/19-private-network-agent-tools/) — The Bicep equivalent this Terraform template is based on
- [Terraform template 15a](../15a-private-network-standard-agent-setup/) — Standard agent private network setup (no MCP subnet)
- [Microsoft Foundry Agent Service networking docs](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/virtual-networks)
- [Models supported by Microsoft Foundry Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/model-region-support)
- [Configure private link for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link)
- [Purge a deleted Cognitive Services resource](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource)
- [AzAPI Provider](https://registry.terraform.io/providers/azure/azapi/latest/docs)
- [azurerm_private_endpoint](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/private_endpoint)

`Tags: Hybrid Networking, Private Endpoints, Advanced`
