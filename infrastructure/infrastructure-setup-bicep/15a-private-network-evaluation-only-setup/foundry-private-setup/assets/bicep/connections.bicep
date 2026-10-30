param accountName string
param projectName string
param storageResourceId string
param applicationInsightsResourceId string = ''
param deployStorageConnection bool = true
param deployMonitoringConnection bool = true
param storageConnectionName string = 'dataset-storage'
param monitoringConnectionName string = 'monitoring'

var storageParts = split(storageResourceId, '/')
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageParts[8]
  scope: resourceGroup(storageParts[2], storageParts[4])
}
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}
resource dataset 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (deployStorageConnection) {
  parent: project
  name: storageConnectionName
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

var insightsParts = split(applicationInsightsResourceId, '/')
resource insights 'Microsoft.Insights/components@2020-02-02' existing = if (!empty(applicationInsightsResourceId)) {
  name: insightsParts[8]
  scope: resourceGroup(insightsParts[2], insightsParts[4])
}
resource monitoring 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = if (!empty(applicationInsightsResourceId) && deployMonitoringConnection) {
  parent: account
  name: monitoringConnectionName
  properties: {
    category: 'AppInsights'
    target: insights!.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: insights!.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: insights!.id
    }
  }
}
