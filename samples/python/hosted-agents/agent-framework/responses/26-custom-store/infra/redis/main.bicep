@description('Location for the Azure Managed Redis cluster. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Name of the Azure Managed Redis cluster. Defaults to a name derived from the resource group.')
param clusterName string = 'amr-${uniqueString(resourceGroup().id)}'

@description('Azure Managed Redis SKU. Balanced_B0 is the smallest tier and is sufficient for this sample.')
param skuName string = 'Balanced_B0'

// Azure Managed Redis (Microsoft.Cache/redisEnterprise). The database uses the
// EnterpriseCluster policy so the four custom stores can run multi-key commands
// (pipelines, sorted sets) against a single logical endpoint without OSS
// cluster hash-slot restrictions.
resource cluster 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: clusterName
  location: location
  sku: {
    name: skuName
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

resource database 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: cluster
  name: 'default'
  properties: {
    accessKeysAuthentication: 'Disabled'
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'EnterpriseCluster'
    evictionPolicy: 'NoEviction'
  }
}

@description('Azure Managed Redis hostname. Consumed by azure.yaml as REDIS_HOST.')
output REDIS_HOST string = cluster.properties.hostName

@description('Azure Managed Redis TLS port. Consumed by azure.yaml as REDIS_PORT.')
output REDIS_PORT string = string(database.properties.port)

@description('Azure Managed Redis database resource ID. Consumed by the postdeploy hook.')
output REDIS_DATABASE_RESOURCE_ID string = database.id
