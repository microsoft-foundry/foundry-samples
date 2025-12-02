param aiFoundryName string
param aiFoundryPrincipal string
param location string
param keyVaultName string
param keyVaultUri string
param keyName string
param keyVersion string
param keyVaultPermissions object = {
  keys: [
    'get'
    'wrapKey'
    'unwrapKey'
    'sign'
    'verify'
    'encrypt'
    'decrypt'
    'wrapKey'
    'unwrapKey'
  ]
  secrets: [
    'get'
    'list'
  ]
}

// Reference account post creation, since we must wait for managed identity to be created to give access to CMK key vault
resource existingAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryName
}
// Reference the existing Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
  name: keyVaultName
}
 
// Add access policy to the Key Vault
resource keyVaultAccessPolicies 'Microsoft.KeyVault/vaults/accessPolicies@2022-07-01' = {
  parent: keyVault
  name: 'add'
  properties: {
    accessPolicies: [
      {
        objectId: aiFoundryPrincipal
        tenantId: subscription().tenantId
        permissions: keyVaultPermissions
      }
    ]
  }
}

// Set customer-managed key encryption on account
resource accountUpdate 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: existingAccount.name
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // new
    encryption: {
      keySource: 'Microsoft.KeyVault'
      keyVaultProperties: {
        keyVaultUri: keyVaultUri
        keyName: keyName
        keyVersion: keyVersion
      }
    }

    // existing properties
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
    customSubDomainName: aiFoundryName
    disableLocalAuth: false
  }
}
