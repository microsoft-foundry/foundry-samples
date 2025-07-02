/*
  AI Foundry account and project - with public network access disabled
  
  Description: 
  - Creates an AI Foundry (previously known as Azure AI Services) account and public network access disabled.
  - Creates a gpt-4o model deployment
*/
@description('That name is the name of our application. It has to be unique. Type a name followed by your resource group name. (<name>-<resourceGroupName>)')
param aiFoundryName string = 'entraid-foundry'

@description('Location for all resources.')
param location string = 'eastus'

@description('Name of the first project')
param projectName string = '${aiFoundryName}-proj'
@description('This project will be a sub-resource of your account')
param projectDescription string = 'A project for the AI Foundry account with storage account'
@description('The display name of the project')
param displayName string = 'project'

@description('Name of the storage account')
param azureStorageName string = 'entraidfoundry'

@description('Storage account sku')
param noZRSRegions array = ['southindia', 'westus']
param sku object = contains(noZRSRegions, location) ? { name: 'Standard_GRS' } : { name: 'Standard_ZRS' }

/* 
  Step 1: Create dependent resource - Storage account
*/
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' =  {
  name: azureStorageName
  location: location
  kind: 'StorageV2'
  sku: sku
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      virtualNetworkRules: []
    }
    allowSharedKeyAccess: false
  }
}

/*
  Step 2: Create an Account
*/
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiFoundryName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // Networking
    publicNetworkAccess: 'Disabled'
    // Specifies whether this resource support project management as child resources, used as containers for access management, data isolation, and cost in AI Foundry.
    allowProjectManagement: true
    // Defines developer API endpoint subdomain
    customSubDomainName: aiFoundryName
    // Auth
    disableLocalAuth: false
  }
}

/* 
  Step 3: Create project
*/
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: displayName
  }

  resource project_connection_azure_storage 'connections@2025-04-01-preview' = {
    name: azureStorageName
    properties: {
      category: 'AzureStorageAccount'
      target: storage.properties.primaryEndpoints.blob
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: storage.id
        location: storage.location
      }
    }
  }
}

/*
  Step 4: Assign storage account roles 
*/

// Storage Blob Data Owner Role
resource storageBlobDataOwner 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'  // Built-in role ID
  scope: resourceGroup()
}

// Assign Storage Blob Data Owner role
resource storageBlobDataOwnerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storageBlobDataOwner.id, storage.id)
  properties: {
    principalId: project.identity.principalId
    roleDefinitionId: storageBlobDataOwner.id
    principalType: 'ServicePrincipal'
  }
}



