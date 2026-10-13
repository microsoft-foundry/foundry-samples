// Explicit Cosmos SQL data-plane grant to the Project MI at database scope.
// This module creates a role assignment, not a database or its containers.

@description('Name of the Cosmos DB account')
param cosmosAccountName string

@description('Principal ID of the Project managed identity')
param projectPrincipalId string

param projectWorkspaceId string

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-12-01-preview' existing = {
  name: cosmosAccountName
  scope: resourceGroup()
}

var roleDefinitionId = resourceId(
  'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions',
  cosmosAccountName,
  '00000000-0000-0000-0000-000000000002'
)

var accountScope = '/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.DocumentDB/databaseAccounts/${cosmosAccountName}/dbs/enterprise_memory'

resource containerRoleAssignmentUserContainer 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2022-05-15' = {
  parent: cosmosAccount
  name: guid(projectWorkspaceId, cosmosAccountName, roleDefinitionId, projectPrincipalId)
  properties: {
    principalId: projectPrincipalId
    roleDefinitionId: roleDefinitionId
    scope: accountScope
  }
}
