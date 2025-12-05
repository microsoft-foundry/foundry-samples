// Parameters for the project module
param accountName string
param projectName string

param containerRegistryName string
param location string = resourceGroup().location
param tags object = {}

param cognitiveServicesSku string = 'S0'

// Container Registry SKU
@allowed(['Basic', 'Standard', 'Premium'])
param containerRegistrySku string = 'Basic'

// Cognitive Services account properties
param publicNetworkAccess string = 'Enabled'

// Cognitive Services Account
resource account 'Microsoft.CognitiveServices/accounts@2025-09-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: cognitiveServicesSku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: publicNetworkAccess
    allowProjectManagement: 'true'
    isAiFoundryType: 'true'
  }
}

// Cognitive Services Project (child resource)
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-09-01' = {
  parent: account
  name: projectName
  location: location
  kind: 'AIServices'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: cognitiveServicesSku
  }
  properties: {
    displayName: projectName
  }
}

// Azure Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: containerRegistryName
  location: location
  tags: tags
  sku: {
    name: containerRegistrySku
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// Built-in AcrPull role definition ID
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

// Role assignment: Grant AcrPull role to the project's system managed identity
resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, project.id, acrPullRoleDefinitionId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

var cognitiveServicesUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')

// Role assignment: Grant AcrPull role to the project's system managed identity
resource cogServicesUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, cognitiveServicesUserRoleDefinitionId)
  scope: account
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  name: 'gpt-4o'
  parent: account
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
}



output acrloginServer string = containerRegistry.properties.loginServer

output foundryProjectEndpoint string = project.properties.endpoints['AI Foundry API']

output foundryProjectPrincipalId string = project.identity.principalId
