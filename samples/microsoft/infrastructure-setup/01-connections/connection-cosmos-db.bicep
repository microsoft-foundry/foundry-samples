/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure Cosmos DB connection.

Run command:
az deployment group create \
  --name AzDeploy \
  --resource-group {RESOURCE-GROUP-NAME} \
  --template-file connection-cosmos-db.bicep \
  --parameters aiFoundryName={FOUNDRY-RESOURCE-NAME}

Optional parameters:
- connectedResourceName: Name of the Cosmos DB account (default: cosmos-{aiFoundryName})
- location: Azure region (default: westus)
- newOrExisting: Whether to create new or use existing Cosmos DB account (default: new)
- isSharedToAll: Share connection with all users (default: true)

Example with all parameters:
az deployment group create --name AzDeploy --resource-group myResourceGroup --template-file connection-cosmos-db.bicep --parameters aiFoundryName=myFoundry connectedResourceName=myCosmosDB location=eastus newOrExisting=existing isSharedToAll=false

*/
param aiFoundryName string = '<your-account-name>'
param connectedResourceName string = 'cosmos-${aiFoundryName}'
param location string = 'westus'

// Whether to create a new Cosmos DB account
@allowed([
  'new'
  'existing'
])
param newOrExisting string = 'new'

// Share connection with all users
param isSharedToAll bool = true

// Refers your existing Azure AI Foundry resource
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Conditionally refers your existing Cosmos DB account
resource existingCosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Handle canary regions for Cosmos DB location
var canaryRegions = ['eastus2euap', 'centraluseuap']
var cosmosDbRegion = contains(canaryRegions, location) ? 'westus' : location

// Conditionally creates a new Cosmos DB account
resource newCosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: cosmosDbRegion
  kind: 'GlobalDocumentDB'
  properties: {
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    disableLocalAuth: true
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    publicNetworkAccess: 'Enabled'
    enableFreeTier: false
    locations: [
      {
        locationName: cosmosDbRegion
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    databaseAccountOfferType: 'Standard'
  }
}

// Creates the Azure Foundry connection to your Cosmos DB account
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-cosmosdb'
  parent: aiFoundry
  properties: {
    category: 'CosmosDb'
    target: ((newOrExisting == 'new') ? newCosmosDB.properties.documentEndpoint : existingCosmosDB.properties.documentEndpoint)
    authType: 'AAD' // Cosmos DB only supports AAD authentication when disableLocalAuth is true
    isSharedToAll: isSharedToAll
    metadata: {
      ApiType: 'Azure'
      ResourceId: ((newOrExisting == 'new') ? newCosmosDB.id : existingCosmosDB.id)
      location: ((newOrExisting == 'new') ? newCosmosDB.location : existingCosmosDB.location)
    }
  }
}
