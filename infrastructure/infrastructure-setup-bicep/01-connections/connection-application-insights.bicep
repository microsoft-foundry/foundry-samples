/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure Application Insights connection.

Only one application insights can be set on a project at a time.
*/
param aiFoundryName string = '<your-foundry-name>'
param connectedResourceName string = 'appi${aiFoundryName}'
param location string = 'westus'

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
resource existingAppInsights 'Microsoft.Insights/components@2020-02-02' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Conditionally creates a new Azure AI Search resource
resource newAppInsights 'Microsoft.Insights/components@2020-02-02' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

// Creates the Azure Foundry connection to your Azure App Insights resource
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-appinsights'
  parent: aiFoundry
  properties: {
    category: 'AppInsights'
    target: ((newOrExisting == 'new') ? newAppInsights.id : existingAppInsights.id)
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: ((newOrExisting == 'new') ? newAppInsights.properties.ConnectionString : existingAppInsights.properties.ConnectionString)
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: ((newOrExisting == 'new') ? newAppInsights.id : existingAppInsights.id)
    }
  }
}
