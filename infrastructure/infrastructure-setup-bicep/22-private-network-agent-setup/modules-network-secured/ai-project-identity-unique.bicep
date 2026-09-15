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

// Add unique connection name parameter
param uniqueConnectionSuffix string = ''

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
    // Scenario 22: capabilitySettings (BYO store resource IDs) makes AccountRP
    // create the project's capability host implicitly. No explicit
    // capabilityHosts resource is declared.
    #disable-next-line BCP037
    capabilitySettings: {
      documentStore: cosmosDBAccount.id
      vectorStore: searchService.id
      blobStore: storageAccount.id
    }
  }

  // Use unique connection names by appending the suffix
}

output projectName string = project.name
output projectId string = project.id
output projectPrincipalId string = project.identity.principalId

#disable-next-line BCP053
output projectWorkspaceId string = project.properties.internalId

// Return the unique connection names
