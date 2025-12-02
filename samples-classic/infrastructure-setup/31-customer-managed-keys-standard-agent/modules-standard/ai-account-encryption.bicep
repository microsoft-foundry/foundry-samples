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
resource existingAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
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
      {
         objectId: 'a232010e-820c-4083-83bb-3ace5fc29d0b' // CosmosDB global applicationID
         tenantId: '72f988bf-86f1-41af-91ab-2d7cd011db47' // Microsoft
         permissions: keyVaultPermissions
      }
    ]
  }
}

// Set customer-managed key encryption on account
resource accountUpdate 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
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
    publicNetworkAccess: 'Disabled'
    allowProjectManagement: true
    customSubDomainName: aiFoundryName
    disableLocalAuth: false
  }
  dependsOn: [
    keyVaultAccessPolicies
  ]
}
