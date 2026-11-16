param location string
param config object

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: config.name
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: config.name
    disableLocalAuth: true
    publicNetworkAccess: config.publicNetworkAccess
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

output resourceId string = account.id
output principalId string = account.identity.principalId
