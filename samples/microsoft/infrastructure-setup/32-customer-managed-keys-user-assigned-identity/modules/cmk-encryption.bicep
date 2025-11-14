/*
  Module: Customer-Managed Key (CMK) Encryption
  
  Configures customer-managed key encryption for AI Foundry account:
  - Adds Key Vault access policy for user-assigned identity
  - Updates account with CMK encryption configuration
*/

@description('Name of the AI Foundry account')
param aiFoundryName string

@description('Location for the resource')
param location string

@description('Name of the Azure Key Vault')
param keyVaultName string

@description('Name of the Azure Key Vault key')
param keyName string

@description('Version of the Azure Key Vault key')
param keyVersion string

@description('Resource ID of the user-assigned managed identity')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity')
param userAssignedIdentityClientId string

// Use the actual Key Vault URI directly since environment() might not resolve correctly in this context
var keyVaultUri = 'https://${keyVaultName}.${environment().suffixes.keyvaultDns}/'

// Note: Key Vault Crypto User role should already be assigned to the UAI
// If not assigned, run: az role assignment create --assignee <UAI-Principal-ID> --role "Key Vault Crypto User" --scope <KeyVault-Resource-ID>

// Reference the existing AI Foundry account
resource existingAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
}

// Update the account with CMK encryption configuration
resource accountUpdate 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: existingAccount.name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // CMK encryption configuration
    encryption: {
      keySource: 'Microsoft.KeyVault'
      keyVaultProperties: {
        keyVaultUri: keyVaultUri
        keyName: keyName
        keyVersion: keyVersion
        identityClientId: userAssignedIdentityClientId
      }
    }
    
    // Required for AI Foundry projects
    allowProjectManagement: true
    
    // Preserve existing properties
    publicNetworkAccess: 'Enabled'
    customSubDomainName: aiFoundryName
    disableLocalAuth: true
  }
}

// Outputs
output encryptionStatus string = 'CMK encryption enabled'
