@description('Name of the Storage Account')
param storageAccountName string

@description('Location for the storage account')
param location string

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_RAGRS'
  }
  kind: 'StorageV2'
  properties: {
    // For Azure AI Foundry BYOS, these settings are required
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true  // Must be true for AI Foundry to access
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    // Required for AI Foundry BYOS
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: false
  }
}

@description('Resource ID of the created storage account')
output storageAccountId string = storageAccount.id

@description('Name of the created storage account')
output storageAccountName string = storageAccount.name
