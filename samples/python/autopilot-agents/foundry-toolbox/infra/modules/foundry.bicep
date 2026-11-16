targetScope = 'resourceGroup'

param location string = resourceGroup().location
param environmentName string
param foundryResourceName string
param foundryResourceExists bool
param foundryProjectName string
param foundryProjectExists bool
param modelDeploymentName string
param modelDeploymentExists bool
param modelName string
param modelFormat string
param modelVersion string
param modelSkuName string
param modelCapacity int

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (!foundryResourceExists) {
  name: foundryResourceName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: {
    'azd-env-name': environmentName
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryResourceName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryAccountReference 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryResourceName
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (!modelDeploymentExists) {
  parent: foundryAccountReference
  name: modelDeploymentName
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
  }
  dependsOn: [
    foundryAccount
  ]
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = if (!foundryProjectExists) {
  parent: foundryAccountReference
  name: foundryProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: foundryProjectName
    description: 'Project provisioned by the ${environmentName} azd environment.'
  }
  dependsOn: [
    foundryAccount
    modelDeployment
  ]
}

resource projectReference 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccountReference
  name: foundryProjectName
}

output AZURE_LOCATION string = projectReference.location
output AZURE_AI_ACCOUNT_NAME string = foundryAccountReference.name
output AZURE_AI_PROJECT_ID string = projectReference.id
output AZURE_AI_PROJECT_NAME string = foundryProjectName
output FOUNDRY_PROJECT_ENDPOINT string = projectReference.properties.endpoints['AI Foundry API']
