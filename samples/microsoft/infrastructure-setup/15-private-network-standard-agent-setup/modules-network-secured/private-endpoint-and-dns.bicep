/*
Private Endpoint and DNS Configuration Module
------------------------------------------
This module configures private network access for Azure services using:

1. Private Endpoints:
   - Creates network interfaces in the specified subnet
   - Establishes private connections to Azure services
   - Enables secure access without public internet exposure

2. Private DNS Zones:
   - Enables custom DNS resolution for private endpoints

3. DNS Zone Links:
   - Links private DNS zones to the VNet
   - Enables name resolution for resources in the VNet
   - Prevents DNS resolution conflicts

Security Benefits:
- Eliminates public internet exposure
- Enables secure access from within VNet
- Prevents data exfiltration through network
*/

// Resource names and identifiers
@description('Name of the AI Foundry account')
param aiAccountName string
@description('Name of the AI Search service')
param aiSearchName string
@description('Name of the storage account')
param storageName string
@description('Name of the Cosmos DB account')
param cosmosDBName string
@description('Name of the Vnet')
param vnetName string
@description('Name of the Customer subnet')
param peSubnetName string
@description('Suffix for unique resource names')
param suffix string


@description('Resource Group name for existing Virtual Network (if different from current resource group)')
param vnetResourceGroupName string = resourceGroup().name

@description('Subscription ID for Virtual Network')
param vnetSubscriptionId string = subscription().subscriptionId

@description('Resource Group name for Storage Account')
param storageAccountResourceGroupName string = resourceGroup().name

@description('Subscription ID for Storage account')
param storageAccountSubscriptionId string = subscription().subscriptionId

@description('Subscription ID for AI Search service')
param aiSearchSubscriptionId string = subscription().subscriptionId

@description('Resource Group name for AI Search service')
param aiSearchResourceGroupName string = resourceGroup().name

@description('Subscription ID for Cosmos DB account')
param cosmosDBSubscriptionId string = subscription().subscriptionId

@description('Resource group name for Cosmos DB account')
param cosmosDBResourceGroupName string = resourceGroup().name
// Reference existing services that need private endpoints
resource aiAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: aiAccountName
  scope: resourceGroup()
}

resource aiSearch 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: aiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
  scope: resourceGroup(storageAccountSubscriptionId, storageAccountResourceGroupName)
}

resource cosmosDBAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: cosmosDBName
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
}

// Reference existing network resources
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: vnetName
  scope: resourceGroup(vnetSubscriptionId, vnetResourceGroupName)
}

resource peSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: peSubnetName
}

/* -------------------------------------------- AI Foundry Account Private Endpoint -------------------------------------------- */

// Private endpoint for AI Services account
// - Creates network interface in customer hub subnet
// - Establishes private connection to AI Services account
resource aiAccountPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${aiAccountName}-private-endpoint'
  location: resourceGroup().location
  properties: {
    subnet: {
      id: peSubnet.id                    // Deploy in customer hub subnet
    }
    privateLinkServiceConnections: [
      {
        name: '${aiAccountName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: aiAccount.id
          groupIds: [
            'account'                     // Target AI Services account
          ]
        }
      }
    ]
  }
}

/* -------------------------------------------- AI Search Private Endpoint -------------------------------------------- */

// Private endpoint for AI Search
// - Creates network interface in customer hub subnet
// - Establishes private connection to AI Search service
resource aiSearchPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${aiSearchName}-private-endpoint'
  location: resourceGroup().location
  properties: {
    subnet: {
      id: peSubnet.id                    // Deploy in customer hub subnet
    }
    privateLinkServiceConnections: [
      {
        name: '${aiSearchName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: aiSearch.id
          groupIds: [
            'searchService'               // Target search service
          ]
        }
      }
    ]
  }
}

/* -------------------------------------------- Storage Private Endpoint -------------------------------------------- */

// Private endpoint for Storage Account
// - Creates network interface in customer hub subnet
// - Establishes private connection to blob storage
resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${storageName}-private-endpoint'
  location: resourceGroup().location
  properties: {
    subnet: {
      id: peSubnet.id                    // Deploy in customer hub subnet
    }
    privateLinkServiceConnections: [
      {
        name: '${storageName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: [
            'blob'                        // Target blob storage
          ]
        }
      }
    ]
  }
}

/*--------------------------------------------- Cosmos DB Private Endpoint -------------------------------------*/

resource cosmosDBPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${cosmosDBName}-private-endpoint'
  location: resourceGroup().location
  properties: {
    subnet: {
      id: peSubnet.id                    // Deploy in customer hub subnet
    }
    privateLinkServiceConnections: [
      {
        name: '${cosmosDBName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: cosmosDBAccount.id
          groupIds: [
            'Sql'                        // Target Cosmos DB account
          ]
        }
      }
    ]
  }
}

/* -------------------------------------------- Private DNS Zones -------------------------------------------- */

// Format: 1) Private DNS Zone
//         2) Link Private DNS Zone to VNet
//         3) Create DNS Zone Group for Private Endpoint

// Private DNS Zone for AI Services (Account)
// 1) Enables custom DNS resolution for AI Services private endpoint

resource aiServicesPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.services.ai.azure.com'
  location: 'global'
}

resource openAiPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
}

resource cognitiveServicesPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
}

// 2) Link AI Services and Azure OpenAI and Cognitive Services DNS Zone to VNet
resource aiServicesLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: aiServicesPrivateDnsZone
  location: 'global'
  name: 'aiServices-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

resource aiOpenAILink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openAiPrivateDnsZone
  location: 'global'
  name: 'aiServicesOpenAI-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

resource cognitiveServicesLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cognitiveServicesPrivateDnsZone
  location: 'global'
  name: 'aiServicesCognitiveServices-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

// 3) DNS Zone Group for AI Services
resource aiServicesDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: aiAccountPrivateEndpoint
  name: '${aiAccountName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: '${aiAccountName}-dns-aiserv-config'
        properties: {
          privateDnsZoneId: aiServicesPrivateDnsZone.id
        }
      }
      {
        name: '${aiAccountName}-dns-openai-config'
        properties: {
          privateDnsZoneId: openAiPrivateDnsZone.id
        }
      }
      {
        name: '${aiAccountName}-dns-cogserv-config'
        properties: {
          privateDnsZoneId: cognitiveServicesPrivateDnsZone.id
        }
      }
    ]
  }
  dependsOn: [
    aiServicesLink
    cognitiveServicesLink
    aiOpenAILink
  ]
}



// Private DNS Zone for AI Search
// 1) Enables custom DNS resolution for AI Search private endpoint
resource aiSearchPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.search.windows.net'  // Standard DNS zone for AI Search
  location: 'global'
}

// 2) Link AI Search DNS Zone to VNet
resource aiSearchLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: aiSearchPrivateDnsZone
  location: 'global'
  name: 'aiSearch-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

// 3) DNS Zone Group for AI Search
resource aiSearchDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: aiSearchPrivateEndpoint
  name: '${aiSearchName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: '${aiSearchName}-dns-config'
        properties: {
          privateDnsZoneId: aiSearchPrivateDnsZone.id
        }
      }
    ]
  }
}

// Private DNS Zone for Storage
// 1) Enables custom DNS resolution for blob storage private endpoint
resource storagePrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.${environment().suffixes.storage}'  // Dynamic DNS zone for storage
  location: 'global'
}

// 2) Link Storage DNS Zone to VNet
resource storageLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: storagePrivateDnsZone
  location: 'global'
  name: 'storage-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

// 3) DNS Zone Group for Storage
resource storageDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: storagePrivateEndpoint
  name: '${storageName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: '${storageName}-dns-config'
        properties: {
          privateDnsZoneId: storagePrivateDnsZone.id
        }
      }
    ]
  }
}


// 1) DNS Zone Group for Cosmos DB

resource cosmosDBPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.documents.azure.com'  // Standard DNS zone for Cosmos DB
  location: 'global'
}

// 2) Link Cosmos DB DNS Zone to VNet
resource cosmosDBLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cosmosDBPrivateDnsZone
  location: 'global'
  name: 'cosmosDB-${suffix}-link'
  properties: {
    virtualNetwork: {
      id: vnet.id                        // Link to specified VNet
    }
    registrationEnabled: false           // Don't auto-register VNet resources
  }
}

// 3) DNS Zone Group for Cosmos DB
resource cosmosDBDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: cosmosDBPrivateEndpoint
  name: '${cosmosDBName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: '${cosmosDBName}-dns-config'
        properties: {
          privateDnsZoneId: cosmosDBPrivateDnsZone.id
        }
      }
    ]
  }
}
