/*
  Module: AI Foundry Account Creation
  
  Creates an Azure AI Foundry account with:
  - User-assigned managed identity
  - Project management enabled
  - System-assigned identity for key vault access
*/

@description('Name of the AI Foundry account')
param aiFoundryName string

@description('Location for the resource')
param location string

@description('Resource ID of the user-assigned managed identity')
param userAssignedIdentityId string

// Identity configuration with only user-assigned identity
var identityConfig = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${userAssignedIdentityId}': {}
  }
}

// Create the AI Foundry account
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiFoundryName
  location: location
  identity: identityConfig
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // Required for AI Foundry projects
    allowProjectManagement: true
    
    // Networking
    publicNetworkAccess: 'Enabled'
    
    // Authentication
    customSubDomainName: aiFoundryName
    disableLocalAuth: true
  }
}

// Outputs
output accountId string = account.id
output accountName string = account.name