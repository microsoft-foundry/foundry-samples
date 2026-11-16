targetScope = 'resourceGroup'

param location string = resourceGroup().location
param accountName string = 'model-ci-${uniqueString(resourceGroup().id)}'

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
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
    customSubDomainName: accountName
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: 'connection-test'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource targetAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: '${accountName}-target'
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: '${accountName}-target'
    disableLocalAuth: true
  }
}

// Exercise the real connection and project-identity role assignment, without model quota.
module sample '../main.bicep' = {
  name: 'foundry-model-sample'
  params: {
    accountName: account.name
    projectName: project.name
    targetAccountResourceId: targetAccount.id
    targetOpenAIBaseUrl: 'https://${targetAccount.name}.services.ai.azure.com/openai/v1'
    modelDeploymentName: 'fixture-model-not-deployed'
    assignBackendRole: true
  }
}

output connectionId string = sample.outputs.connectionId
output roleAssignmentId string = sample.outputs.roleAssignmentId
