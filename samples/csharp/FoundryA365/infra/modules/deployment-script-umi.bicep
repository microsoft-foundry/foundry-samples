targetScope = 'resourceGroup'

@description('Name of the User Assigned Managed Identity to create')
param identityName string = 'foundry-deployment-script-umi'

//
// 1. Create the user-assigned identity
//
resource umi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: resourceGroup().location
}

//
// 2. Grant Contributor role on this resource group
//
resource contributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, umi.id, 'Contributor')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'b24988ac-6180-42a0-ab88-20f7382dd24c' // Contributor Role ID
    )
    principalId: umi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

var cognitiveServicesUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')

// Role assignment: Grant AcrPull role to the project's system managed identity
resource cogServicesUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, umi.id, cognitiveServicesUserRoleDefinitionId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalId: umi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}


//
// Optional: Output the identity info
//
output uamiClientId string = umi.properties.clientId
output uamiPrincipalId string = umi.properties.principalId
output uamiResourceId string = umi.id
