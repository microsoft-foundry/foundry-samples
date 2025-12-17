@description('The name of the AI Services account')
param accountName string

@description('The isolation mode for the managed network')
@allowed([
  'AllowOnlyApprovedOutbound'
  'AllowInternetOutbound'
])
param isolationMode string = 'AllowOnlyApprovedOutbound'

@description('The name of the storage account to create outbound rules for')
param storageName string

@description('The resource group name where the storage account is located')
param storageResourceGroupName string

@description('The subscription ID where the storage account is located')
param storageSubscriptionId string

// @description('The name of the AI Search service to create outbound rules for')
// param aiSearchName string

// @description('The resource group name where the AI Search service is located')
// param aiSearchResourceGroupName string

// @description('The subscription ID where the AI Search service is located')
// param aiSearchSubscriptionId string

// @description('The name of the Cosmos DB account to create outbound rules for')
// param cosmosDBName string

// @description('The resource group name where the Cosmos DB account is located')
// param cosmosDBResourceGroupName string

// @description('The subscription ID where the Cosmos DB account is located')
// param cosmosDBSubscriptionId string

// Reference the existing AI Services account in the same resource group
resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

// Create the managed network settings first
#disable-next-line BCP081
resource managedNetwork 'Microsoft.CognitiveServices/accounts/managednetworks@2025-10-01-preview' = {
  parent: aiAccount
  name: 'default'
  properties: {
    managedNetwork: {
      IsolationMode: isolationMode
      managedNetworkKind: 'V2'
      //firewallSku: 'Standard' // Uncomment to enable firewall only when in AllowOnlyApprovedOutbound mode
    }
  }
}

// Create outbound rule for Storage Account
#disable-next-line BCP081
resource storageOutboundRule 'Microsoft.CognitiveServices/accounts/managednetworks/outboundRules@2025-10-01-preview' = {
  parent: managedNetwork
  name: 'storage-outbound-rule'
  properties: {
    type: 'PrivateEndpoint'
    destination: {
      serviceResourceId: '/subscriptions/${storageSubscriptionId}/resourceGroups/${storageResourceGroupName}/providers/Microsoft.Storage/storageAccounts/${storageName}'
      subresourceTarget: 'blob'
      sparkEnabled: false
      sparkStatus: 'Inactive'
    }
    category: 'UserDefined'
  }
}

// // Create outbound rule for AI Search
// #disable-next-line BCP081
// resource aiSearchOutboundRule 'Microsoft.CognitiveServices/accounts/managednetworks/outboundRules@2025-10-01-preview' = {
//   parent: managedNetwork
//   name: 'aisearch-outbound-rule'
//   properties: {
//     type: 'PrivateEndpoint'
//     destination: {
//       serviceResourceId: '/subscriptions/${aiSearchSubscriptionId}/resourceGroups/${aiSearchResourceGroupName}/providers/Microsoft.Search/searchServices/${aiSearchName}'
//       subresourceTarget: 'searchService'
//       sparkEnabled: false
//       sparkStatus: 'Inactive'
//     }
//     category: 'UserDefined'
//   }
// }

// // Create outbound rule for Cosmos DB
// #disable-next-line BCP081
// resource cosmosDBOutboundRule 'Microsoft.CognitiveServices/accounts/managednetworks/outboundRules@2025-10-01-preview' = {
//   parent: managedNetwork
//   name: 'cosmosdb-outbound-rule'
//   properties: {
//     type: 'PrivateEndpoint'
//     destination: {
//       serviceResourceId: '/subscriptions/${cosmosDBSubscriptionId}/resourceGroups/${cosmosDBResourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/${cosmosDBName}'
//       subresourceTarget: 'Sql'
//       sparkEnabled: false
//       sparkStatus: 'Inactive'
//     }
//     category: 'UserDefined'
//   }
// }

output managedNetworkSettingsName string = managedNetwork.name
output storageOutboundRuleName string = storageOutboundRule.name
// output aiSearchOutboundRuleName string = aiSearchOutboundRule.name
// output cosmosDBOutboundRuleName string = cosmosDBOutboundRule.name
