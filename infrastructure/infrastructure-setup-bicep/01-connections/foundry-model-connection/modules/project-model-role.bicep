targetScope = 'resourceGroup'

@description('Existing target Foundry account in this module deployment resource group.')
param targetAccountName string

@description('Principal/object ID of the source project managed identity, not the account identity or the deploying user.')
param projectPrincipalId string

// Foundry User (Azure AI User).
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource targetAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: targetAccountName
}

resource projectModelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: targetAccount
  name: guid(targetAccount.id, projectPrincipalId, foundryUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output roleAssignmentId string = projectModelRole.id
