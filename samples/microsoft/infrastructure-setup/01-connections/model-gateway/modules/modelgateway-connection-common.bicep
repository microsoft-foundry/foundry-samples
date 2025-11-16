/*
Common module for creating ModelGateway connections to Azure AI Foundry projects.
This module handles the core connection logic and can be reused across different ModelGateway connection samples.
ModelGateway connections support ApiKey authentication.
*/

// Project resource parameters
param projectResourceId string
param connectionName string

// ModelGateway target configuration
param targetUrl string

// Connection configuration (ModelGateway only supports ApiKey)
param authType string = 'ApiKey'
param isSharedToAll bool = false

// API key for the ModelGateway endpoint
@secure()
param apiKey string

// ModelGateway-specific metadata (passed through from parent template)
param metadata object

// Extract project information from resource ID
var aiFoundryName = split(projectResourceId, '/')[8]
var projectName = split(projectResourceId, '/')[10]

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

// Create the ModelGateway connection with ApiKey authentication
resource connectionApiKey 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  name: connectionName
  parent: aiProject
  properties: {
    category: 'ModelGateway'
    target: targetUrl
    authType: 'ApiKey'
    isSharedToAll: isSharedToAll
    credentials: {
      key: apiKey
    }
    metadata: metadata
  }
}

// Outputs
output connectionName string = connectionApiKey.name
output connectionId string = connectionApiKey.id
output targetUrl string = targetUrl
output authType string = authType
output metadata object = metadata
