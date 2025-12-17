---
description: This set of templates demonstrates how to set up Azure AI Agent Service with managed virtual network isolation with private network links to connect the agent to your secure data.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: managed-network-secured-agent
languages:
- bicep
- json
---

# Azure AI Agent Service: Standard Agent Setup with Managed Virtual Network

---
## Overview
This infrastructure-as-code (IaC) solution deploys a network-secured Azure AI agent environment with private networking and role-based access control (RBAC).

Standard setup supports private network isolation through utilizing **Managed Virtual Network** approach. Managed Virtual Network support is a public preview feature and requires a feature flag to allowlst your subscription. Preview feature is titled "AI.ManagedVnetPreview" in the Azure Portal

---

## Deploy to Azure

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F18-managed-virtual-network-preview%2Fazuredeploy.json)

---

## Prerequisites

1. **Register your subscription with the Preview Features in Azure Portal for Managed VNET**
  - The feature is titled "AI.ManagedVnetPreview" in the Azure Portal under "Preview Features". Register your subscription for the preview. It will take a few hours to approve your subscription. 

1. **Active Azure subscription with appropriate permissions**
   - **Azure AI Account Owner**: Needed to create a Foundry account and project 
   - **Owner or Role Based Access Administrator**: Needed to assign RBAC to the required resources (Cosmos DB, Azure AI Search, Storage) 
   - **Azure AI User**: Needed to create and edit agents

1. Azure CLI installed and configured on your local workstation or deployment pipeline server. Azure CLI support is required to run the 'az rest' commands to update your managed virtual network. 

1. **Register Resource Providers**

   Make sure you have an active Azure subscription that allows registering resource providers. If it's not already registered, run the commands below:

   ```bash
   az provider register --namespace 'Microsoft.KeyVault'
   az provider register --namespace 'Microsoft.CognitiveServices'
   az provider register --namespace 'Microsoft.Storage'
   az provider register --namespace 'Microsoft.Search'
   az provider register --namespace 'Microsoft.Network'
   az provider register --namespace 'Microsoft.ContainerService'
   ```

1. Network administrator permissions (if operating in a restricted or enterprise environment)

1. Sufficient quota for all resources in your target Azure region
    * If no parameters are passed in, this template creates an Azure AI Foundry resource, Foundry project, Azure Cosmos DB for NoSQL, Azure AI Search, and Azure Storage account

---

## Pre-Deployment Steps

### Limitations 
1. A managed network Foundry resource is only deployable via the `main.bicep` template in the folder `18-managed-virtual-network-preview` in foundry-samples.
1. If you create FQDN outbound rules when the managed virtual network is in Allow Only Approved Outbound mode, a managed Azure Firewall is created which comes with associated Firewall costs. The FQDN outbound rules only support ports 80 and 443. 
1. Managed virtual network isolation cannot be disabled after enabling. There is no upgrade path from custom virtual network set-up to managed virtual network. A Foundry resource redeployment is required. Deleting your Foundry resource deletes the managed virtual network.
1. Outbound rules from the managed network must be created through Azure CLI. For the end-to-end secured Agent service set-up with a managed virtual network, the template creates the managed private endpoint to the associated Storage account. Private endpoints are not created to CosmosDB or AI Search. Please use instructions in the `outbound rules CLI ` for information on how to create the managed private endpoints.
1. Support for managed virtual network is only in the following regions: **East US, East US2, Japan East, France Central, UAE North, Brazil South, Spain Central, Germany West Central, Italy North, South Central US, West Central US, Australia East, Sweden Central, Canada East, South Africa North, West Europe, West US, West US 3, South India, and UK South.**
1. If you require private access to on-premises resources for your Foundry resource, please use the to [Application Gatway](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/access-on-premises-resources?view=foundry-classic&viewFallbackFrom=foundry) to configure on-premises access. The same set-up with a private endpoint to Application Gateway and setting up backend pools is supported. Both L4 and L7 traffic are now supported with the Application Gateway in GA.
1. Supports only Standard BYO resources Agents v1 and the Foundry classic experience. Basic Agents do not require network isolation. Support in the new Agents v2 and the new Foundry UI is coming soon. 
1. End-to-end network isolation for Agent MCP tools with managed virtual network is currently not supported. Please use public MCP tools with managed network isolation Foundry. 
1. For any feedback, please directly email meerakurup@microsoft.com 

### Template Customization

Note: If not provided, the following resources will be created automatically for you:
- VNet and one subnet
- Azure Cosmos DB for NoSQL  
- Azure AI Search
- Azure Storage

**Optional Integration:** API Management services can be integrated by providing an existing API Management service resource ID.

#### Parameters

1. **Use Existing Virtual Network and Subnets**

To use an existing VNet and subnet, set the existingVnetResourceId parameter to the full Azure Resource ID of the target VNet and its address range, and provide the names of the required subnet.  If the existing VNet is associated with private DNS zones, set the existingDnsZones parameter to the resource group name in which the zones are located. For example:
- param existingVnetResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>"
- param peSubnetName string = 'pe-subnet' //optional, default is 'pe-subnet'
- param peSubnetPrefix string = '192.168.1.0/24' //optional, default is '192.168.1.0/24'
- param existingDnsZones = {
       
         'privatelink.services.ai.azure.com': 'privzoneRG' //add resource group name where your private DNS zone is located
       
         'privatelink.openai.azure.com': '' //Leave empty to create new private dns zone... }

💡 If subnets information is provided then make sure it exist within the specified VNet to avoid deployment errors. If subnet information is not provided, the template will create subnets with the default address space.


2. **Use an existing Azure Cosmos DB for NoSQL**

To use an existing Cosmos DB for NoSQL resource, set cosmosDBResourceId parameter to the full Azure Resource ID of the target Cosmos DB.
- param azureCosmosDBAccountResourceId string =  /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/{cosmosDbAccountName}


3. **Use an existing Azure AI Search resource**

To use an existing Azure AI Search resource, set aiSearchServiceResourceId parameter to the full Azure resource Id of the target Azure AI Search resource. 
 - param aiSearchResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Search/searchServices/{searchServiceName}


4. **Use an existing Azure Storage account**

To use an existing Azure Storage account, set aiStorageAccountResourceId parameter to the full Azure resource Id of the target Azure Storage account resource. 
- param aiStorageAccountResourceId string = /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}

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

> **Note:** To access your Foundry resource securely, use either a VM, VPN, or ExpressRoute.

---

## Network Secured Agent Project Architecture Deep Dive

### Core Components

**Azure AI Foundry** resource
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

By bundling these BYO features (file storage, search, and thread storage), the standard setup guarantees that your deployment is secure by default. All data processed by Azure AI Foundry Agent Service is automatically stored at rest in your own Azure resources, helping you meet internal policies, compliance requirements, and enterprise security standards.

### Azure Resources Created

Azure AI Foundry (Cognitive Services)
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

### Network Security Design

Network Security
- Public network access disabled
- Private endpoints for all services
- Network ACLs with deny by default

**Network Infrastructure**
- A Virtual Network (192.168.0.0/16) is created (if existing isn't passed in)
- Private endpoint Subnet (192.168.1.0/24): Hosts private endpoints

**Private Endpoints** 
Private endpoints ensure secure, internal-only connectivity. Private endpoints are created for the following:
- Azure AI Foundry
- Azure AI Search
- Azure Storage
- Azure Cosmos DB

**Private DNS Zones**
| Private Link Resource Type | Sub Resource | Private DNS Zone Name | Public DNS Zone Forwarders |
|----------------------------|--------------|------------------------|-----------------------------|
| **Azure AI Foundry**       | account      | `privatelink.cognitiveservices.azure.com`<br>`privatelink.openai.azure.com`<br>`privatelink.services.ai.azure.com` | `cognitiveservices.azure.com`<br>`openai.azure.com`<br>`services.ai.azure.com` |
| **Azure AI Search**        | searchService| `privatelink.search.windows.net` | `search.windows.net` |
| **Azure Cosmos DB**        | Sql          | `privatelink.documents.azure.com` | `documents.azure.com` |
| **Azure Storage**          | blob         | `privatelink.blob.core.windows.net` | `blob.core.windows.net` |


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
    - Cosmos DB Built-in Data Contributor(`00000000-0000-0000-0000-000000000002`)
  - **Azure AI Foundry Resource**
    - Contributor (`b24988ac-6180-42a0-ab88-20f7382dd24c`) Required role for the Foundry account to accept all private endpoints created in the managed VNET. This role will be updated to the Azure AI Enterprise Network Connection Approver role which has a smaller scope. 
---

## Module Structure

```text
modules-network-secured/
├── add-project-capability-host.bicep               # Configuring the project's capability host
├── ai-account-identity.bicep                       # Azure AI Foundry deployment and configuration
├── ai-project-identity.bicep                       # Foundry project deployment and connection configuration           
├── ai-search-role-assignments.bicep                # AI Search RBAC configuration
├── azure-storage-account-role-assignment.bicep     # Storage Account RBAC configuration  
├── blob-storage-container-role-assignments.bicep   # Blob Storage Container RBAC configuration
├── cosmos-container-role-assignments.bicep         # CosmosDB container Account RBAC configuration
├── cosmosdb-account-role-assignment.bicep          # CosmosDB Account RBAC configuration
├── existing-vnet.bicep                             # Bring your existing virtual network to template deployment
├── format-project-workspace-id.bicep               # Formatting the project workspace ID
├── managed-network.bicep                           # Managed virtual network and outbound rules configuration
├── network-agent-vnet.bicep                        # Logic for routing virtual network set-up if existing virtual network is selected
├── private-endpoint-and-dns.bicep                  # Creating private endpoints and DNS zones for dependent resources
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

- [Azure AI Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Azure AI Foundry RBAC Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
- Managed virtual network (public documentation coming soon)
