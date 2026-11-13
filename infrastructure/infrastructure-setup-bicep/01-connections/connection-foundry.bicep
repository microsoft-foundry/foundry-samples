/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure AI Foundry connection.

Run command:
az deployment group create \
  --name AzDeploy \
  --resource-group {RESOURCE-GROUP-NAME} \
  --template-file connection-foundry.bicep \
  --parameters aiFoundryName={FOUNDRY-RESOURCE-NAME}

Optional parameters:
- connectedResourceName: Name of the target Azure AI Foundry resource (default: foundry-{aiFoundryName})
- location: Target account location (default: deployment resource group location)
- newOrExisting: Whether to create new or use existing Azure AI Foundry resource (default: new)
- authType: Authentication type - ApiKey or AAD (default: ApiKey)
- isSharedToAll: Share connection with all users (default: true)

Example with all parameters:
az deployment group create --name AzDeploy --resource-group myResourceGroup --template-file connection-foundry.bicep --parameters aiFoundryName=myFoundry connectedResourceName=myTargetFoundry location=westus3 newOrExisting=new authType=AAD isSharedToAll=false

*/
param aiFoundryName string = '<your-account-name>'
param connectedResourceName string = 'foundry-${aiFoundryName}'
@allowed([
  'australiaeast'
  'brazilsouth'
  'canadacentral'
  'canadaeast'
  'centralindia'
  'centralus'
  'eastasia'
  'eastus'
  'francecentral'
  'germanywestcentral'
  'italynorth'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'northeurope'
  'norwayeast'
  'qatarcentral'
  'southafricanorth'
  'southcentralus'
  'southindia'
  'southeastasia'
  'spaincentral'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westeurope'
  'westus'
  'westus3'
  'usgovarizona'
  'usgovvirginia'
])
param location string = any(resourceGroup().location)

// Whether to create a new Azure AI Foundry resource
@allowed([
  'new'
  'existing'
])
param newOrExisting string = 'new'

// Supported authentication types
@allowed([
  'ApiKey'
  'AAD'
])
param authType string = 'ApiKey'

// Share connection with all users
param isSharedToAll bool = true

// Refers your existing Azure AI Foundry resource (source)
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Conditionally refers your existing target Azure AI Foundry resource
resource existingFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Conditionally creates a new target Azure AI Foundry resource
resource newFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {}
}

// Creates the Azure Foundry connection to your target Azure AI Foundry resource
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-foundry'
  parent: aiFoundry
  properties: {
    category: 'AIServices'
    target: ((newOrExisting == 'new') ? newFoundry.properties.endpoint : existingFoundry.properties.endpoint)
    authType: authType // Supported auth types: ApiKey, AAD
    isSharedToAll: isSharedToAll
    credentials: authType == 'ApiKey' ? {
      key: ((newOrExisting == 'new') ? newFoundry.listKeys().key1 : existingFoundry.listKeys().key1)
    } : {}
    metadata: {
      ApiType: 'Azure'
      ResourceId: ((newOrExisting == 'new') ? newFoundry.id : existingFoundry.id)
      location: ((newOrExisting == 'new') ? newFoundry.location : existingFoundry.location)
    }
  }
}
