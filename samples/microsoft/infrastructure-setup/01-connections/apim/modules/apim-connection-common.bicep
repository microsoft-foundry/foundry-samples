/*
Common module for creating APIM connections to Azure AI Foundry projects.
This module handles the core connection logic and can be reused across different APIM connection samples.
*/

// Project resource parameters
param projectResourceId string
param connectionName string

// APIM resource parameters  
param apimResourceId string
param apiName string
param apimSubscriptionName string = 'master'

// Connection configuration
param authType string = 'ApiKey'
param isSharedToAll bool = false

// APIM-specific metadata (passed through from parent template)
param metadata object

// Extract project information from resource ID
var aiFoundryName = split(projectResourceId, '/')[8]
var projectName = split(projectResourceId, '/')[10]

// Extract APIM information from resource ID
var apimSubscriptionId = split(apimResourceId, '/')[2]
var apimResourceGroupName = split(apimResourceId, '/')[4]
var apimServiceName = split(apimResourceId, '/')[8]

// Reference the AI Foundry account
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Reference the project within the AI Foundry account
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  name: projectName
  parent: aiFoundry
}

// Reference the APIM service (can be in different resource group/subscription)
resource existingApim 'Microsoft.ApiManagement/service@2021-08-01' existing = {
  name: apimServiceName
  scope: resourceGroup(apimSubscriptionId, apimResourceGroupName)
}

// Reference the specific API within APIM
resource apimApi 'Microsoft.ApiManagement/service/apis@2021-08-01' existing = {
  name: apiName
  parent: existingApim
}

// Reference the APIM subscription to get keys (only for ApiKey auth)
resource apimSubscription 'Microsoft.ApiManagement/service/subscriptions@2021-08-01' existing = {
  name: apimSubscriptionName
  parent: existingApim
}

// Create the connection with ApiKey authentication
resource connectionApiKey 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (authType == 'ApiKey') {
  name: connectionName
  parent: aiProject
  properties: {
    category: 'ApiManagement'
    target: '${existingApim.properties.gatewayUrl}/${apimApi.properties.path}'
    authType: 'ApiKey'
    isSharedToAll: isSharedToAll
    credentials: {
      key: apimSubscription.listSecrets(apimSubscription.apiVersion).primaryKey
    }
    metadata: metadata
  }
}

// TODO: Future AAD connection (when role assignments are implemented)
// resource connectionAAD 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (authType == 'AAD') {
//   name: connectionName
//   parent: aiProject
//   properties: {
//     category: 'ApiManagement'
//     target: '${existingApim.properties.gatewayUrl}/${apimApi.properties.path}'
//     authType: 'AAD'
//     isSharedToAll: isSharedToAll
//     credentials: {}
//     metadata: metadata
//   }
// }

// Outputs (only from the created connection)
output connectionName string = authType == 'ApiKey' ? connectionApiKey.name : ''
output connectionId string = authType == 'ApiKey' ? connectionApiKey.id : ''
output targetUrl string = '${existingApim.properties.gatewayUrl}/${apimApi.properties.path}'
output authType string = authType
output metadata object = metadata
