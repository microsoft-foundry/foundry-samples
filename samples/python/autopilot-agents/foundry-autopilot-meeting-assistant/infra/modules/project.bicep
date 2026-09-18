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

param deployModel bool = false
param modelDeploymentName string
param modelName string
param modelVersion string
param modelSkuName string
param modelCapacity int

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
    allowProjectManagement: true
  }
}

// Cognitive Services Project (child resource)
resource project 'Microsoft.CognitiveServices/accounts/projects@2026-03-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
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

var meetingDelegateStorageAccountName = '${take(toLower(replace(accountName, '-', '')), 11)}${uniqueString(subscription().id, resourceGroup().id, 'meeting')}'

resource meetingDelegateStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: meetingDelegateStorageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource meetingDelegateBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: meetingDelegateStorageAccount
  name: 'default'
}

resource meetingDelegateContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: meetingDelegateBlobService
  name: 'meeting-delegates'
  properties: {
    publicAccess: 'None'
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

// Role assignment: Grant AcrPull role to the account's system managed identity
resource accountAcrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, account.id, acrPullRoleDefinitionId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: account.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployModel) {
  name: modelDeploymentName
  parent: account
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}


output acrloginServer string = containerRegistry.properties.loginServer

output foundryProjectEndpoint string = project.properties.endpoints['AI Foundry API']

output foundryProjectResourceId string = project.id

output foundryProjectPrincipalId string = project.identity.principalId

output foundryAccountResourceId string = account.id

output deployedModelResponsesEndpoint string = 'https://${account.name}.services.ai.azure.com/openai/v1/responses'

output meetingDelegateStorageAccountUrl string = meetingDelegateStorageAccount.properties.primaryEndpoints.blob

output meetingDelegateStorageAccountId string = meetingDelegateStorageAccount.id

output meetingDelegateStorageContainerName string = meetingDelegateContainer.name

