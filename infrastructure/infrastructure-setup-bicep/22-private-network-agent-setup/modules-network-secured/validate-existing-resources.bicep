@description('Optional resource ID of the AI Search service.')
param aiSearchResourceId string

@description('Optional resource ID of the Azure Storage account.')
param azureStorageAccountResourceId string

@description('Optional resource ID of the Cosmos DB account.')
param azureCosmosDBAccountResourceId string

@description('Optional resource ID of the virtual network.')
param existingVnetResourceId string = ''

@description('Optional resource ID of the Cognitive Services account.')
param existingAiFoundryAccountResourceId string = ''

@description('Object mapping DNS zone names to their resource group, or empty string to indicate creation.')
param existingDnsZones object

@description('Subscription ID where existing private DNS zones are located.')
#disable-next-line no-unused-params
param dnsZonesSubscriptionId string

@description('List of private DNS zone names to validate.')
param dnsZoneNames array

var resources = [
  {
    id: azureStorageAccountResourceId
    type: 'Microsoft.Storage/storageAccounts'
  }
  {
    id: aiSearchResourceId
    type: 'Microsoft.Search/searchServices'
  }
  {
    id: azureCosmosDBAccountResourceId
    type: 'Microsoft.DocumentDB/databaseAccounts'
  }
  {
    id: existingVnetResourceId
    type: 'Microsoft.Network/virtualNetworks'
  }
  {
    id: existingAiFoundryAccountResourceId
    type: 'Microsoft.CognitiveServices/accounts'
  }
]

var resourceParts = [for item in resources: {
  id: item.id
  expectedType: split(toLower(item.type), '/')
  parts: split(item.id, '/')
}]

// Keep all indexed accesses safe even when the supplied path is malformed.
var safeParts = [for item in resourceParts: {
  id: item.id
  expectedType: item.expectedType
  hasNineParts: length(item.parts) == 9
  parts: length(item.parts) == 9 ? item.parts : ['', '', '', '', '', '', '', '', '']
}]

var resourceChecks = [for item in safeParts: {
  omitted: empty(item.id)
  hasNineParts: item.hasNineParts
  prefix: item.parts[0] == '' && toLower(item.parts[1]) == 'subscriptions'
  subscription: length(item.parts[2]) == 36 ? reduce(range(0, 36), true, (valid, i) => valid && (contains([8, 13, 18, 23], i) ? substring(item.parts[2], i, 1) == '-' : contains('0123456789abcdef', toLower(substring(item.parts[2], i, 1))))) : false
  resourceGroup: toLower(item.parts[3]) == 'resourcegroups' && !empty(item.parts[4]) && trim(item.parts[4]) == item.parts[4]
  provider: toLower(item.parts[5]) == 'providers' && toLower(item.parts[6]) == item.expectedType[0] && toLower(item.parts[7]) == item.expectedType[1]
  name: !empty(item.parts[8]) && trim(item.parts[8]) == item.parts[8]
  safeCharacters: !contains(item.id, '?') && !contains(item.id, '#') && !contains(item.id, '%') && !contains(item.id, ' ') && !contains(item.id, '\\') && !contains(item.id, '\t') && !contains(item.id, '\r') && !contains(item.id, '\n')
}]

var validResourceIds = [for check in resourceChecks: check.omitted || (check.hasNineParts && check.prefix && check.subscription && check.resourceGroup && check.provider && check.name && check.safeCharacters)]

// ARM parameter allowed-values validation fails the nested deployment with the
// offending parameter's explanatory value before any validated ID is returned.
module idGuard 'validate-resource-id-guard.bicep' = {
  params: {
    storageStatus: any(validResourceIds[0] ? 'valid' : 'Invalid storage ID: expected /subscriptions/<guid>/resourceGroups/<group>/providers/Microsoft.Storage/storageAccounts/<name>')
    searchStatus: any(validResourceIds[1] ? 'valid' : 'Invalid Search ID: expected /subscriptions/<guid>/resourceGroups/<group>/providers/Microsoft.Search/searchServices/<name>')
    cosmosStatus: any(validResourceIds[2] ? 'valid' : 'Invalid Cosmos DB ID: expected /subscriptions/<guid>/resourceGroups/<group>/providers/Microsoft.DocumentDB/databaseAccounts/<name>')
    vnetStatus: any(validResourceIds[3] ? 'valid' : 'Invalid VNet ID: expected /subscriptions/<guid>/resourceGroups/<group>/providers/Microsoft.Network/virtualNetworks/<name>')
    accountStatus: any(validResourceIds[4] ? 'valid' : 'Invalid account ID: expected /subscriptions/<guid>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<name>')
    resourceIds: [for item in resources: item.id]
  }
}

var storageId = idGuard.outputs.resourceIds[0]
var searchId = idGuard.outputs.resourceIds[1]
var cosmosId = idGuard.outputs.resourceIds[2]
var storageParts = split(storageId, '/')
var searchParts = split(searchId, '/')
var cosmosParts = split(cosmosId, '/')

// These compatibility outputs indicate that an ID was supplied, not that the
// target exists. A subsequent resource operation may fail if it does not.
output azureStorageExists bool = !empty(storageId)
output aiSearchExists bool = !empty(searchId)
output cosmosDBExists bool = !empty(cosmosId)

output azureStorageSubscriptionId string = empty(storageId) ? subscription().subscriptionId : storageParts[2]
output azureStorageResourceGroupName string = empty(storageId) ? resourceGroup().name : storageParts[4]
output aiSearchServiceSubscriptionId string = empty(searchId) ? subscription().subscriptionId : searchParts[2]
output aiSearchServiceResourceGroupName string = empty(searchId) ? resourceGroup().name : searchParts[4]
output cosmosDBSubscriptionId string = empty(cosmosId) ? subscription().subscriptionId : cosmosParts[2]
output cosmosDBResourceGroupName string = empty(cosmosId) ? resourceGroup().name : cosmosParts[4]

output validatedStorageResourceId string = storageId
output validatedSearchResourceId string = searchId
output validatedCosmosResourceId string = cosmosId
output validatedVnetResourceId string = idGuard.outputs.resourceIds[3]
output validatedAccountResourceId string = idGuard.outputs.resourceIds[4]

// This reports configuration, not the result of an existence check.
output dnsZoneExists array = [
  for zoneName in dnsZoneNames: {
    name: zoneName
    exists: !empty(existingDnsZones[?zoneName] ?? '')
  }
]
