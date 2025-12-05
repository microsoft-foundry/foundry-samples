/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure Application Insights connection.

Only one application insights can be set on a project at a time.
*/
param aiFoundryName string = '<your-foundry-name>'
param connectedResourceName string = 'st${aiFoundryName}'
param location string = 'global'
param apiKey string = '<your-key>'

// Whether to create a new Azure AI Search resource
@allowed([
  'new'
  'existing'
])
param newOrExisting string = 'new'
 
// Refers your existing Azure AI Foundry resource
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Conditionally refers your existing Azure AI Search resource
resource existing 'Microsoft.Bing/accounts@2020-06-10' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Conditionally creates a new Azure AI Search resource
resource new 'Microsoft.Bing/accounts@2020-06-10' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: location
  sku: {
    name: 'G1'
  }
  properties: {
    statisticsEnabled: false
  }
  kind: 'Bing.Grounding'
}

// Creates the Azure Foundry connection to your Azure App Insights resource
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-bing'
  parent: aiFoundry
  properties: {
    category: 'ApiKey'
    target: 'https://api.bing.microsoft.com/'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: apiKey
    }
    metadata: {
      ApiType: 'Azure'
      Type: 'bing_grounding'
      ResourceId: ((newOrExisting == 'new') ? new.id : existing.id)
    }
  }
}
