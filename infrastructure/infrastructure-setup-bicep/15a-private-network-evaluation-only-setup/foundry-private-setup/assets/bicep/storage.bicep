param location string
param config object

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: config.name
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: config.publicNetworkAccess
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: []
      ipRules: []
    }
  }
}

output resourceId string = storage.id
// Reading through the module output waits for Storage provisioning.
output blobEndpoint string = storage.properties.primaryEndpoints.blob
