targetScope = 'resourceGroup'

param location string = resourceGroup().location
param accountName string = 'header-ci-${uniqueString(resourceGroup().id)}'
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'

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

// ARM persistence smoke test, not a live gateway or model inference test.
module sample '../main.bicep' = {
  name: 'secret-header-sample'
  params: {
    accountName: account.name
    projectName: project.name
    targetUrl: 'https://gateway.example.invalid/openai'
    audience: 'api://connection-fixture'
    modelDeploymentName: modelName
    modelName: modelName
    modelVersion: modelVersion
    subscriptionKey: 'fixture-only-not-a-real-subscription-key'
  }
}

output connectionId string = sample.outputs.connectionId
output secretHeaderConnectionId string = sample.outputs.secretHeaderConnectionId
