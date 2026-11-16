param location string
param accountName string
param config object

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: config.name
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: config.name
    description: 'Private network evaluation setup'
  }
}

output resourceId string = project.id
output principalId string = project.identity.principalId
