param accountName string
param location string
// param modelName string
// param modelFormat string
// param modelVersion string
// param modelSkuName string
// param modelCapacity int

#disable-next-line BCP036

//AIO Mode managed virtual network 
resource account 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    networkAcls: {
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Disabled'
    networkInjections: [
      {
        scenario: 'agent'
        subnetArmId: ''
        useMicrosoftManagedNetwork: true
      }
    ]
    disableLocalAuth: false
  }
}

// Role assignment for the AI Services account managed identity, Azure AI Network connection approver role / Contributor (Change back when available)
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, 'b24988ac-6180-42a0-ab88-20f7382dd24c', resourceGroup().id)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: account.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// #disable-next-line BCP081
// resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview'=  {
//   parent: account
//   name: modelName
//   sku : {
//     capacity: modelCapacity
//     name: modelSkuName
//   }
//   properties: {
//     model:{
//       name: modelName
//       format: modelFormat
//       version: modelVersion
//     }
//   }
// }

output accountName string = account.name
output accountID string = account.id
output accountTarget string = account.properties.endpoint
output accountPrincipalId string = account.identity.principalId
