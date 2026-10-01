// PUT the named Project with capabilitySettings and three explicit child
// connections. Unlike an `existing` reference, this writes project metadata and
// identity. Supply the current values when preserving them, and verify the parent
// account is already network injected. No explicit host or RBAC resource is in this module.

param accountName string
param projectName string

@description('Azure region of the existing project. Required because scenario 22 applies capabilitySettings via a project upsert.')
param location string

@description('Display name to preserve on the existing project (pass the current value to avoid changing it).')
param displayName string

@description('Description written to the Project. Pass the current value to preserve it; the empty default clears an existing description.')
param projectDescription string = ''

param aiSearchName string
param aiSearchServiceResourceGroupName string
param aiSearchServiceSubscriptionId string

param cosmosDBName string
param cosmosDBSubscriptionId string
param cosmosDBResourceGroupName string

param azureStorageName string
param azureStorageSubscriptionId string
param azureStorageResourceGroupName string

@description('Name of the explicit Cosmos DB connection to create or update. This does not select the implicit host binding; verify existing managed connections and returned bindings.')
param cosmosDBConnectionName string

@description('Name of the explicit Storage connection to create or update. This does not select the implicit host binding; verify existing managed connections and returned bindings.')
param azureStorageConnectionName string

@description('Name of the explicit AI Search connection to create or update. This does not select the implicit host binding; verify existing managed connections and returned bindings.')
param aiSearchConnectionName string

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
  scope: resourceGroup(aiSearchServiceSubscriptionId, aiSearchServiceResourceGroupName)
}
resource cosmosDBAccount 'Microsoft.DocumentDB/databaseAccounts@2024-12-01-preview' existing = {
  name: cosmosDBName
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
}
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: azureStorageName
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
}

resource account 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' existing = {
  name: accountName
  scope: resourceGroup()
}

// A network-injected parent is required for implicit provisioning. This Project
// PUT selects stores and writes the supplied metadata; omitted description is not
// automatically preserved. RBAC is created by other enabled modules or an operator.
resource project 'Microsoft.CognitiveServices/accounts/projects@2026-05-15-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: displayName
    description: projectDescription
    #disable-next-line BCP037
    capabilitySettings: {
      documentStore: cosmosDBAccount.id
      vectorStore: searchService.id
      blobStore: storageAccount.id
    }
  }

  // Explicit connection PUTs. Do not assume an implicit host adopts these names
  // or that service-managed connections can be overwritten.
  resource project_connection_cosmosdb_account 'connections@2026-05-15-preview' = {
    name: cosmosDBConnectionName
    properties: {
      category: 'CosmosDB'
      target: cosmosDBAccount.properties.documentEndpoint
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: cosmosDBAccount.id
        location: cosmosDBAccount.location
      }
    }
  }

  resource project_connection_azure_storage 'connections@2026-05-15-preview' = {
    name: azureStorageConnectionName
    properties: {
      category: 'AzureStorageAccount'
      target: storageAccount.properties.primaryEndpoints.blob
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: storageAccount.id
        location: storageAccount.location
      }
    }
  }

  resource project_connection_azureai_search 'connections@2026-05-15-preview' = {
    name: aiSearchConnectionName
    properties: {
      category: 'CognitiveSearch'
      target: 'https://${aiSearchName}.search.windows.net'
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: searchService.id
        location: searchService.location
      }
    }
  }
}

output projectName string = project.name
output projectId string = project.id
output projectPrincipalId string = project.identity.principalId

#disable-next-line BCP053
output projectWorkspaceId string = project.properties.internalId

// Return explicitly requested connection names; not a read of implicit host bindings.
output cosmosDBConnection string = cosmosDBConnectionName
output azureStorageConnection string = azureStorageConnectionName
output aiSearchConnection string = aiSearchConnectionName
