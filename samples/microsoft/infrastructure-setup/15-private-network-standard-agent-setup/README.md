---
description: This set of templates demonstrates how to set up Azure AI Agent Service with virtual network isolation with private network links to connect the agent to your secure data.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent
languages:
- bicep
- json
---

# Azure AI Agent Service: Standard Agent Setup with E2E Network Isolation

This infrastructure-as-code (IaC) solution deploys a network-secured Azure AI agent environment with private networking and role-based access control (RBAC).

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Fsamples%2Fmicrosoft%2Finfrastructure-setup%2F15-private-network-standard-agent-setup%2Fazuredeploy.json)

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
  - **Azure AI Account Owner**: Needed to create a cognitive services account and project 
  - **Owner or Role Based Access Administrator**: Needed to assign RBAC to the required resources (Cosmos DB, Azure AI Search, Storage) 
  - **Azure AI User**: Needed to create and edit agents 

2. **Register Resource Providers**

   Make sure you have an active Azure subscription that allows registering resource providers. For example, subnet delegation requires the Microsoft.App provider to be registered in your subscription. If it's not already registered, run the commands below:

   ```bash
   az provider register --namespace 'Microsoft.KeyVault'
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Storage'
   az provider register --namespace 'Microsoft.MachineLearningServices'
   az provider register --namespace 'Microsoft.Search'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.App'
   az provider register --namespace 'Microsoft.ContainerService'
   ```

3. Network administrator permissions (if operating in a restricted or enterprise environment) 

4. Sufficient quota for all resources in your target Azure region 

5. Azure CLI installed and configured on your local workstation or deployment pipeline server 

## Pre-Deployment Steps

1. Review network requirements and plan Virtual Network address space (e.g., 192.168.0.0/16 or an alternative non-overlapping address space) 

2. Two subnets are needed as well:  
  - **Agent Subnet** (e.g., 192.168.0.0/24): Hosts Agent client for Agent workloads 
  - **Private endpoint Subnet** (e.g. 192.168.1.0/24): Hosts private endpoints 
    - Ensure that the address spaces for these subnets do not overlap with any existing networks in your Azure environment 
  
  > **Note:** If you do not provide an existing virtual network, the template will create a new virtual network with the address spaces and subnets described above. If you use an existing virtual network, make sure it already contains two subnets (Agent and Private Endpoint) before deploying the template.

  **Limitations:**
  - Class A subnet support is only available in a limited number of regions and requires your subscription id be allowlisted. Please reach out to fosteramanda@microsoft.com if you are interested in getting access.
    - Regions with class A support: westus, eastus us, eastus 2, and central us 

---

## Template Customization

Note: If not provided, the following resources will be created automatically for you: 
- VNet and two subnets 
- Azure Cosmos DB for NoSQL  
- Azure AI Search 
- Azure Storage 

### Parameters

1. Use Existing Virtual Network and Subnets 
To use an existing VNet and subnets, set the existingVnetResourceId parameter to the full Azure Resource ID of the target VNet, and provide the names of the two required subnets. Example: 
- param ExistingVnetResourceI = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>" 
- param agentSubnetName string = 'agent-subnet' 
- param peSubnetName string = 'pe-subnet' 

💡 Ensure both subnets already exist within the specified VNet. If they do not, you must also set createAgentSubnet and/or createPeSubnet to true and provide valid CIDR prefixes for creation. 

2. Use an existing Azure Cosmos DB for NoSQL 
To use an existing Cosmos DB for NoSQL resource, set cosmosDBResourceId parameter to the full Azure Resource ID of the target Cosmos DB. 
- param cosmosDBResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName} 

3. Use an existing Azure AI Search resource 
To use an existing Azure AI Search resource, set aiSearchServiceResourceId parameter to the full Azure resource Id of the target Azure AI Search resource. 
- param aiSearchServiceResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Search/searchServices/{searchServiceName} 


4. Use an existing Azure Storage account 
To use an existing Azure Storage account, set aiStorageAccountResourceId parameter to the full Azure resource Id of the target Azure Storage account resource. 
- param aiStorageAccountResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName} 

 
## Deploy the bicep template

1. Option 1: Click the deploy to Azure button above to open the Azure portal and deploy the template directly.
  - Fill in the parameters as needed, including the existing VNet and subnets if applicable. 

2. Option 2: Manually deploy the bicep template
**Create a New (or Use Existing) Resource Group**

   ```bash
   az group create --name <new-rg-name> --location <your-rg-region>
   ```

3. **Deploy the main.bicep**

   ```bash
   az deployment group create --resource-group <new-rg-name> --template-file main.bicep
   ```

> **Note:** To access your Foundry resource securely, use either a VM, VPN, or ExpressRoute.

## Architecture Overview

For more details on the networking set-up, see our documentation on [Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/virtual-networks).

### Step by Step Provisioning Process
Standard Setup Network Secured Steps for main.bicep
-----------------------------------
1. Create dependent resources for standard setup:
   - Create new (or pass in resource ID of existing) Cosmos DB resource
   - Create new (or pass in resource ID of existing) Azure Storage resource
   - Create new (or pass in resource ID of existing) Azure AI Search resource
   - Create new (or pass in resource ID of existing) Virtual Network resource
   - [Optional] Create a new Key Vault resource
   - [Optional] Create new Application Insights resource
   - [Optional] Pass in resource ID of existing AI Foundry resource


2. Create Azure AI Foundry Resource (Cognitive Services/accounts, kind=AIServices)

3. Create account-level connections:
   - Create account connection to Application Insights resource
   - Deploy GPT-4o or other agent-compatible model

4. Create Project (Cognitive Services/accounts/project)

5. Create project connections:
   - Create project connection to Azure Storage account
   - Create project connection to Azure AI Search account
   - Create project connection to Cosmos DB account

6. Assign the project-managed identity (including for SMI) the following roles:
   - Cosmos DB Operator at the scope of the account level for the Cosmos DB account resource
   - Storage Account Contributor at the scope of the account level for the Storage Account resource

7. Set Account capability host with empty properties section.

8. Set Project capability host with properties: Cosmos DB, Azure Storage, AI Search connections

9. Assign the Project Managed Identity (both for SMI and UMI) the following roles on the specified resource scopes:
   - Azure AI Search: Search Index Data Contributor, Search Service Contributor
   - Azure Blob Storage Container: <workspaceId>-azureml-blobstore: Storage Blob Data Contributor
   - Azure Blob Storage Container: <workspaceId>-agents-blobstore: Storage Blob Data Owner
   - Cosmos DB for NoSQL container: <'${projectWorkspaceId}>-thread-message-store: Cosmos DB Built-in Data Contributor
   - Cosmos DB for NoSQL container: <'${projectWorkspaceId}>-system-thread-message-store: Cosmos DB Built-in Data Contributor
   - Cosmos DB for NoSQL container: <'${projectWorkspaceId}>-agent-entity-store: Cosmos DB Built-in Data Contributor

10. Once all resources are provisioned, assign all developers who want to create/edit agents in the project the role: Azure AI User on the project scope.

The deployment creates an isolated network environment:

- If you don't bring an existing virtual network, the following will be created for you **Virtual Network (192.168.0.0/16):**
  - Agent Subnet (192.168.0.0/24): Hosts Agent client for Agent workloads
  - Private endpoint Subnet (192.168.1.0/24): Hosts private endpoints

- **Private Endpoints:**
  - AI Foundry
  - AI Search
  - CosmosDB
  - Storage

- **Private DNS Zones:**
  - privatelink.blob.core.windows.net
  - privatelink.cognitiveservices.azure.com
  - privatelink.documents.azure.com
  - privatelink.file.core.windows.net
  - privatelink.openai.azure.com
  - privatelink.search.windows.net
  - privatelink.services.ai.azure.com

### Core Components

1. **AI Foundry Resource**
   - Central orchestration point
   - Manages service connections
   - Network-isolated capability hosts
2. **AI Project**
   - Workspace configuration
   - Service integration
   - Agent deployment
3. **Supporting Services for Standard Agent Deployment**
   - Azure AI Search
   - CosmosDB
   - Storage Account

---

## Security Features

### Authentication & Authorization

- **Managed Identity**
  - Zero-trust security model
  - No credential storage
  - Platform-managed rotation

- **Role Assignments**
  - **Azure AI Search**
    - Search Index Data Contributor (`8ebe5a00-799e-43f5-93ac-243d3dce84a7`)
    - Search Service Contributor (`7ca78c08-252a-4471-8644-bb5ff32d4ba0`)
  - **Azure Storage Account**
    - Storage Blob Data Owner (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`)
    - Storage Queue Data Contributor (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`) (if Azure Function tool enabled)
    - Two containers will automatically be provisioned during the create capability host process:
      - Azure Blob Storage Container: `<workspaceId>-azureml-blobstore`
        - Storage Blob Data Contributor
      - Azure Blob Storage Container: `<workspaceId>-agents-blobstore`
        - Storage Blob Data Owner
  - **Key Vault**
    - Key Vault Contributor (`f25e0fa2-a7c8-4377-a976-54943a77a395`)
    - Key Vault Secrets Officer (`b86a8fe4-44ce-4948-aee5-eccb2c155cd7`)
  - **Cosmos DB for NoSQL**
    - Cosmos DB Operator (`230815da-be43-4aae-9cb4-875f7bd000aa`)
    - Cosmos DB Built-in Data Contributor
    - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-thread-message-store`
    - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-agent-entity-store`

### Network Security

- Public network access disabled
- Private endpoints for all services
- Service endpoints for Azure services
- Network ACLs with deny by default

---

## Deployment Options

> **Note:** Currently the only deployment option is through this Bicep template.

### Infrastructure as Code (Bicep)

1. **Create a New (or Use Existing) Resource Group:**

   ```bash
   az group create --name <new-rg-name> --location <your-rg-region>
   ```

2. **Deploy the main.bicep:**

   ```bash
   az deployment group create --resource-group <new-rg-name> --template-file main.bicep
   ```

---

## Module Structure

```text
modules-network-secured/
├── add-project-capability-host.bicep               # Configuring the project's capability host
├── ai-account-identity.bicep                       # Setting the account's RBAC configurations
├── ai-project-identity.bicep                       # Setting the project's RBAC configurations            
├── ai-search-role-assignments.bicep                # AI Search RBAC configuration
├── azure-storage-account-role-assignments.bicep    # Storage Account RBAC configuration  
├── blob-storage-container-role-assignments.bicep   # Blob Storage Container RBAC configuration
├── cosmos-container-role-assignments.bicep         # CosmosDB container Account RBAC configuration
├── cosmosdb-account-role-assignment.bicep          # CosmosDB Account RBAC configuration
├── existing-vnet.bicep                             # Bring your existing virtual network to template deployment
├── format-project-workspace-id.bicep               # Formatting the project workspace ID
├── network-agent-vnet.bicep                        # Logic for routing virtual network set-up if existing virtual network is selected
├── private-endpoint-and-dns.bicep                  # Creating virtual networks and DNS zones. 
├── standard-dependent-resources.bicep              # Deploying CosmosDB, Storage, and Search
├── subnet.bicep                                    # Setting the subnet for Agent network injection
├── validate-existing-resources.bicep               # Validate existing CosmosDB, Storage, and Search to template deployment
└── vnet.bicep                                      # Deploying a new virtual network
```

> **Note:** If you bring your own VNET for this template, ensure the subnet for Agents has the correct subnet delegation to `Microsoft.App/environments`. If you have not specified the delegated subnet, the template will complete this for you.

---

## Limitations

- The capability host sub-resources of resource/Project must be deleted before deleting the resource/Project resource itself. You can use the script as sample to delete it or can be done in alternate ways via ARM. This restriction will be removed in the next revision (coming soon).
    - [Run delete script](../utils/deleteCaphost.sh)
- If you want to delete your Foundry resource and Standard Agent with secured network set-up from the Azure Portal, delete your AI Foundry resource and virtual network last. Before deleting the virtual network, ensure to delete and purge your AI Foundry resource. Navigate to **Manage deleted resources**, then select your subscription and the Foundry resource you would like to purge.

---

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

- [Azure AI Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Azure AI Foundry RBAC Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
