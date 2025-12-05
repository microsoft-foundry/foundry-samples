/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure OpenAI connection.

Run command:
az deployment group create \
  --name AzDeploy \
  --resource-group {RESOURCE-GROUP-NAME} \
  --template-file connection-azure-openai.bicep \
  --parameters aiFoundryName={FOUNDRY-RESOURCE-NAME}

Optional parameters:
- connectedResourceName: Name of the Azure OpenAI resource (default: aoai-{aiFoundryName})
- location: Azure region (default: westus)
- newOrExisting: Whether to create new or use existing Azure OpenAI resource (default: new)
- authType: Authentication type - ApiKey or AAD (default: ApiKey)
- isSharedToAll: Share connection with all users (default: true)

Example with all parameters:
az deployment group create --name AzDeploy --resource-group myResourceGroup --template-file connection-azure-openai.bicep --parameters aiFoundryName=myFoundry connectedResourceName=myOpenAI location=eastus newOrExisting=existing authType=AAD isSharedToAll=false

*/
param aiFoundryName string = '<your-account-name>'
param connectedResourceName string = 'aoai-${aiFoundryName}'
param location string = 'westus'

// Whether to create a new Azure OpenAI resource
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

// Refers your existing Azure AI Foundry resource
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Conditionally refers your existing Azure OpenAI resource
resource existingOpenAI 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Conditionally creates a new Azure OpenAI resource
resource newOpenAI 'Microsoft.CognitiveServices/accounts@2023-05-01' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {}
}

// Creates the Azure Foundry connection to your Azure OpenAI resource
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-openai'
  parent: aiFoundry
  properties: {
    category: 'AzureOpenAI'
    target: ((newOrExisting == 'new') ? newOpenAI.properties.endpoint : existingOpenAI.properties.endpoint)
    authType: authType // Supported auth types: ApiKey, AAD
    isSharedToAll: isSharedToAll
    credentials: authType == 'ApiKey' ? {
      key: ((newOrExisting == 'new') ? newOpenAI.listKeys().key1 : existingOpenAI.listKeys().key1)
    } : {}
    metadata: {
      ApiType: 'Azure'
      ResourceId: ((newOrExisting == 'new') ? newOpenAI.id : existingOpenAI.id)
      location: ((newOrExisting == 'new') ? newOpenAI.location : existingOpenAI.location)
    }
  }
}
