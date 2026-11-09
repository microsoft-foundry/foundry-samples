/*
Application Insights Role Assignment Module

  Log Analytics Reader               73c42c96-874c-492b-b04d-ab87d138a893
  Privileged Monitoring Data Reader  dbc9c667-e97f-4491-aee6-90b9cf960190
*/

@description('Name of the Application Insights component to grant access on.')
param appInsightsName string

@description('Principal (object) ID of the project managed identity.')
param projectPrincipalId string

@description('Built-in role definition GUIDs to assign. Defaults to Log Analytics Reader + Privileged Monitoring Data Reader (the latter is required to query GenAI content).')
param roleDefinitionGuids array = [
  '73c42c96-874c-492b-b04d-ab87d138a893'
  'dbc9c667-e97f-4491-aee6-90b9cf960190'
]

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
  scope: resourceGroup()
}

resource appInsightsRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleGuid in roleDefinitionGuids: {
  scope: appInsights
  name: guid(projectPrincipalId, roleGuid, appInsights.id)
  properties: {
    principalId: projectPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleGuid)
    principalType: 'ServicePrincipal'
  }
}]