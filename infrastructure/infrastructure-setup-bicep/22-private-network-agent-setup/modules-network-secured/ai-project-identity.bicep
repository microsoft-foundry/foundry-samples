param accountName string
param location string
param projectName string
param projectDescription string
param displayName string

param aiSearchName string
param aiSearchServiceResourceGroupName string
param aiSearchServiceSubscriptionId string

param cosmosDBName string
param cosmosDBSubscriptionId string
param cosmosDBResourceGroupName string

param azureStorageName string
param azureStorageSubscriptionId string
param azureStorageResourceGroupName string

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

resource project 'Microsoft.CognitiveServices/accounts/projects@2026-05-15-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: displayName
    // Scenario 22: declaring capabilitySettings (the BYO store ARM resource IDs)
    // makes AccountRP auto-provision the project's connections and its capability
    // host implicitly. This template therefore declares NO explicit
    // Microsoft.CognitiveServices/accounts/projects/capabilityHosts resource.
    // documentStore -> thread storage (Cosmos DB), vectorStore -> AI Search,
    // blobStore -> Storage account.
    // Bicep type defs for projects@2026-05-15-preview do not yet model
    // capabilitySettings; the ARM API accepts it, so suppress the BCP037 false positive.
    #disable-next-line BCP037
    capabilitySettings: {
      documentStore: cosmosDBAccount.id
      vectorStore: searchService.id
      blobStore: storageAccount.id
    }
  }

}

output projectName string = project.name
output projectId string = project.id
output projectPrincipalId string = project.identity.principalId

#disable-next-line BCP053
output projectWorkspaceId string = project.properties.internalId

// return the BYO connection names
output cosmosDBConnection string = cosmosDBName
output azureStorageConnection string = azureStorageName
output aiSearchConnection string = aiSearchName
