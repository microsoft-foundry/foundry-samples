@description('Name of the Storage Account')
param storageAccountName string

@description('Principal ID of the AI Foundry managed identity')
param principalId string

@description('AI Foundry resource ID for generating unique role assignment name')
param aiFoundryResourceId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(aiFoundryResourceId, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
 