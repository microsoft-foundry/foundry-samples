/*
Common module for creating ModelGateway connections to Azure AI Foundry projects.
This module handles the core connection logic and can be reused across different ModelGateway connection samples.
ModelGateway connections support ApiKey and Oauth2.0 client credentials authentication.
*/

// Project resource parameters
param projectResourceId string
param connectionName string

// ModelGateway target configuration
param targetUrl string

// Connection configuration (ModelGateway supports ApiKey and OAuth2)
@allowed(['ApiKey', 'OAuth2'])
param authType string = 'ApiKey'
param isSharedToAll bool = false

// API key for the ModelGateway endpoint (required for ApiKey auth)
@secure()
param apiKey string = ''

// OAuth2 parameters (required for OAuth2 auth)
@secure()
param clientId string = ''
@secure()
param clientSecret string = ''
param tokenUrl string = ''
param scopes array = []

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
resource connectionApiKey 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (authType == 'ApiKey') {
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

// Create the ModelGateway connection with OAuth2 authentication
resource connectionOAuth2 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (authType == 'OAuth2') {
  name: connectionName
  parent: aiProject
  properties: any({
    category: 'ModelGateway'
    target: targetUrl
    authType: 'OAuth2'
    isSharedToAll: isSharedToAll
    credentials: {
      clientId: clientId
      clientSecret: clientSecret
    }
    tokenUrl: tokenUrl
    scopes: scopes
    metadata: metadata
  })
}

// Outputs
output connectionName string = authType == 'ApiKey' ? connectionApiKey.name : connectionOAuth2.name
output connectionId string = authType == 'ApiKey' ? connectionApiKey.id : connectionOAuth2.id
output targetUrl string = targetUrl
output authType string = authType
output metadata object = metadata
