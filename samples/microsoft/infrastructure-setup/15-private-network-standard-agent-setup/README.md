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

> **IMPORTANT**
> 
> Class A subnet support is only available in a limited number of regions and requires your subscription id be allowlisted. Please reach out to fosteramanda@microsoft.com if you are interested in getting access.
 **Supported regions: West US, East US, East US 2, Japan East, France Central, UAE North, Brazil South, Germany West Central, Italy North, South Central US, Australia East, Sweden Central, South Africa North**
>
> Class B and C subnet support is already GA and available in all regions supported by Azure AI Foundry Agent Service. No subscription allowlisting is required. Deployment templates and setup steps are identical for Class A, B, and C subnets; Class A remains in private preview solely because of its limited region coverage. For more on the supported regions of the Azure AI Foundry Agent service, see [Models supported by Azure AI Foundry Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/model-region-support?tabs=global-standard)

---
## Overview
This infrastructure-as-code (IaC) solution deploys a network-secured Azure AI agent environment with private networking and role-based access control (RBAC).

Standard setup supports private network isolation through utilizing **Bring Your Own Virtual Network (BYO VNet)** approach, also known as **custom VNet support with subnet delegation.** 

This implementation gives you full control over the inbound and outbound communication paths for your agent. You can restrict access to only the resources explicitly required by your agent, such as storage accounts, databases, or APIs, while blocking all other traffic by default. This approach ensures that your agent operates within a tightly scoped network boundary, reducing the risk of data leakage or unauthorized access. By default, this setup simplifies security configuration while enforcing strong isolation guarantees, ensuring that each agent deployment remains secure, compliant, and aligned with enterprise networking policies. 

---

## Key Information

**Limited Region Support for Class A Subnet IPs**
- Class A subnet support is only available in select regions and requires allowlisting of your subscription ID. **Supported regions: West US, East US, East US 2, Central US, Japan East, France Central, Spain Central, UAE North**

**Region and Resource Placement Requirements**
- **All Foundry workspace resources should be in the same region as the VNet**, including CosmosDB, Storage Account, AI Search, Foundry Account, Project, Managed Identity. The only exception is within the Foundry Account, you may choose to deploy your model to a different region, and any cross-region communication will be handled securely within our network infrastructure.
  - **Note:** Your Virtual Network can be in a different resource group than your Foundry workspace resources 


[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fazure-ai-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Fsamples%2Fmicrosoft%2Finfrastructure-setup%2F15-private-network-standard-agent-setup%2Fazuredeploy.json)

---

## Prerequisites

1. **Active Azure subscription with appropriate permissions**
   - **Azure AI Account Owner**: Needed to create a cognitive services account and project 
   - **Owner or Role Based Access Administrator**: Needed to assign RBAC to the required resources (Cosmos DB, Azure AI Search, Storage) 
   - **Azure AI User**: Needed to create and edit agents

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

1. Sufficient quota for all resources in your target Azure region
    * If no parameters are passed in, this template creates an Azure AI Foundry resource, Foundry project, Azure Cosmos DB for NoSQL, Azure AI Search, and Azure Storage account
1. Azure CLI installed and configured on your local workstation or deployment pipeline server

---

## Pre-Deployment Steps

### Networking Requirements
1. Review network requirements and plan Virtual Network address space (e.g., 192.168.0.0/16 or an alternative non-overlapping address space)

2. Two subnets are needed as well:  
    - **Agent Subnet** (e.g., 192.168.0.0/24): Hosts Agent client for Agent workloads, delegated to Microsoft.App/environments. The recommended size should be /24 for this delegated subnet. 
    - **Private endpoint Subnet** (e.g. 192.168.1.0/24): Hosts private endpoints 
    - Ensure that the address spaces for these subnets do not overlap with any existing networks in your Azure environment or reserved IP ranges like the following: 169.254.0.0/16, 172.30.0.0/16, 172.31.0.0/16, 192.0.2.0/24, 0.0.0.0/8, 127.0.0.0/8, 100.100.0.0/17, 100.100.192.0/19, 100.100.224.0/19, 10.0.0.0/8.
  
  > **Notes:** 
  - If you do not provide an existing virtual network, the template will create a new virtual network with the default address spaces and subnets described above. If you use an existing virtual network, make sure it already contains two subnets (Agent and Private Endpoint) before deploying the template.
  - You must ensure the Foundry account was successfully created so that underlying caphost has also succeeded. Then proceed to deploying the project caphost bicep. 
  - You must ensure the subnet is not already in use by another account. It must be an exclusive subnet for the Foundry account.
  - You must ensure the subnet is exclusively delegated to __Microsoft.App/environments__ and cannot be used by any other Azure resources.
  

  **Limitations:**
  - Class A subnet support is only available in a limited number of regions and requires your subscription id be allowlisted. Please reach out to fosteramanda@microsoft.com if you are interested in getting access.
    - Supported regions: West US, East US, East US 2, Central US, Japan East, France Central, [New] Spain Central, [New] UAE North
  - The capability host sub-resources of Resource/Project must be deleted before deleting the Resource/Project resource itself. You can use the script __deleteCaphost.sh__ located in this folder to delete it.  


### Template Customization

Note: If not provided, the following resources will be created automatically for you:
- VNet and two subnets
- Azure Cosmos DB for NoSQL  
- Azure AI Search
- Azure Storage

#### Parameters

1. **Use Existing Virtual Network and Subnets**

To use an existing VNet and subnets, set the existingVnetResourceId parameter to the full Azure Resource ID of the target VNet and its address range, and provide the names of the two required subnets.  If the existing VNet is associated with private DNS zones, set the existingDnsZones parameter to the resource group name in which the zones are located. For example:
- param existingVnetResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Network/virtualNetworks/<vnet-name>"
- param agentSubnetName string = 'agent-subnet' //optional, default is 'agent-subnet'
- param agentSubnetPrefix string = '192.168.0.0/24' //optional, default is '192.168.0.0/24'
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
    - Cosmos DB Built-in Data Contributor
    - Three containers will automatically be provisioned during the create capability host process:
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-thread-message-store`
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-system-thread-message-store`
      - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-agent-entity-store`


---

## Module Structure

```text
modules-network-secured/
├── add-project-capability-host.bicep               # Configuring the project's capability host
├── ai-account-identity.bicep                       # Azure AI Foundry deployment and configuration
├── ai-project-identity.bicep                       # Foundry project deployment and connection configuration           
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
