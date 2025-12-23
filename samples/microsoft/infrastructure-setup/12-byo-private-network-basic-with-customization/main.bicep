/*
  Combined AI Foundry deployment with private networking and BYO Azure OpenAI connection.

  Description:
  - Creates an AI Foundry account with public network access disabled and private connectivity resources.
  - Creates a project with a connection to an existing Azure OpenAI resource.
  - Configures account and project capability hosts bound to the connection.
  - Deploys a sample GPT-4o model deployment in the AI Foundry account.
  - Reuses an existing virtual network and private endpoint subnet for private connectivity.
*/
param azureDeployName string = utcNow()

@maxLength(9)
@description('Base name for the AI Foundry account. A random suffix is appended to ensure uniqueness.')
param accountBaseName string = 'foundry'

var aiFoundryName string = '${accountBaseName}${substring(uniqueString(azureDeployName), 0, 4)}'

@allowed([
  'australiaeast'
  'canadaeast'
  'eastus'
  'eastus2'
  'francecentral'
  'japaneast'
  'koreacentral'
  'norwayeast'
  'polandcentral'
  'southindia'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westus'
  'westus3'
  'westeurope'
  'southeastasia'
])
@description('The Azure region where the AI Foundry account and related resources will be created.')
param location string = 'eastus'

@description('Name of the project to create within the AI Foundry account.')
param projectName string = '${accountBaseName}${substring(uniqueString(azureDeployName), 0, 4)}-proj'

@description('Display name of the project to create within the AI Foundry account.')
param projectDisplayName string = 'Project Display Name'

@description('Description for the project to create within the AI Foundry account.')
param projectDescription string = 'Sample project provisioned by Bicep.'

@description('Resource ID of the existing virtual network that will host the private endpoint.')
param existingVnetResourceId string

@description('Resource ID of the existing subnet dedicated to private endpoints.')
param existingPeSubnetResourceId string

@description('Resource ID of the existing Azure OpenAI resource to connect to the project.')
param existingAoaiResourceId string

var byoAoaiConnectionName string = 'aoaiConnection'
var accountCapabilityHostName string = '${aiFoundryName}-capHost'

// Break down existing virtual network and subnet resource IDs for reuse scopes.
var existingVnetResourceIdParts = split(existingVnetResourceId, '/')
var existingVnetSubscriptionId = existingVnetResourceIdParts[2]
var existingVnetResourceGroupName = existingVnetResourceIdParts[4]
var existingVnetName = existingVnetResourceIdParts[8]

var existingPeSubnetResourceIdParts = split(existingPeSubnetResourceId, '/')
var existingPeSubnetName = existingPeSubnetResourceIdParts[10]

// Break down the Azure OpenAI resource ID to extract subscription, resource group, and resource name.
var existingAoaiResourceIdParts = split(existingAoaiResourceId, '/')
var existingAoaiResourceSubscriptionId = existingAoaiResourceIdParts[2]
var existingAoaiResourceGroupName = existingAoaiResourceIdParts[4]
var existingAoaiAccountName = existingAoaiResourceIdParts[8]

// Reference the existing Azure OpenAI resource.
resource existingAoaiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  scope: resourceGroup(existingAoaiResourceSubscriptionId, existingAoaiResourceGroupName)
  name: existingAoaiAccountName
}

// Create the AI Foundry account with private network access only.
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiFoundryName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: aiFoundryName
    disableLocalAuth: false
    publicNetworkAccess: 'Disabled'
  }
}

// Reference existing virtual network components that will host private endpoints for the account.
resource existingVirtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  scope: resourceGroup(existingVnetSubscriptionId, existingVnetResourceGroupName)
  name: existingVnetName
}

resource existingPeSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: existingVirtualNetwork
  name: existingPeSubnetName
}

// Private endpoint configuration for the AI Foundry account.
resource aiAccountPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${aiFoundryName}-private-endpoint'
  location: location
  properties: {
    subnet: {
      id: existingPeSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: '${aiFoundryName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: account.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

// Private DNS zones required for the AI Foundry and Azure OpenAI endpoints.
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

// Link each private DNS zone to the existing virtual network.
resource aiServicesLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: aiServicesPrivateDnsZone
  location: 'global'
  name: 'aiServices-link'
  properties: {
    virtualNetwork: {
      id: existingVirtualNetwork.id
    }
    registrationEnabled: false
  }
}

resource aiOpenAILink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openAiPrivateDnsZone
  location: 'global'
  name: 'aiServicesOpenAI-link'
  properties: {
    virtualNetwork: {
      id: existingVirtualNetwork.id
    }
    registrationEnabled: false
  }
}

resource cognitiveServicesLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cognitiveServicesPrivateDnsZone
  location: 'global'
  name: 'aiServicesCognitiveServices-link'
  properties: {
    virtualNetwork: {
      id: existingVirtualNetwork.id
    }
    registrationEnabled: false
  }
}

// Associate the private endpoint with the DNS zones to enable private name resolution.
resource aiServicesDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: aiAccountPrivateEndpoint
  name: '${aiFoundryName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: '${aiFoundryName}-dns-aiserv-config'
        properties: {
          privateDnsZoneId: aiServicesPrivateDnsZone.id
        }
      }
      {
        name: '${aiFoundryName}-dns-openai-config'
        properties: {
          privateDnsZoneId: openAiPrivateDnsZone.id
        }
      }
      {
        name: '${aiFoundryName}-dns-cogserv-config'
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

// Create a project within the AI Foundry account and configure the BYO Azure OpenAI connection.
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectDisplayName
  }

  resource byoAoaiConnection 'connections@2025-04-01-preview' = {
    name: byoAoaiConnectionName
    properties: {
      category: 'AzureOpenAI'
      target: existingAoaiResource.properties.endpoint
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: existingAoaiResource.id
        location: existingAoaiResource.location
      }
    }
  }
}

// Configure capability hosts so the project can leverage the Azure OpenAI connection.
resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  name: accountCapabilityHostName
  parent: account
  properties: {
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    project
    project::byoAoaiConnection
  ]
}

resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: '${project.name}-capHost'
  parent: project
  properties: {
    capabilityHostKind: 'Agents'
    aiServicesConnections: [
      byoAoaiConnectionName
    ]
  }
  dependsOn: [
    accountCapabilityHost
    project::byoAoaiConnection
  ]
}

output accountId string = account.id
output accountName string = account.name
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
output projectConnectionName string = resourceId('Microsoft.CognitiveServices/accounts/projects/connections', account.name, project.name, byoAoaiConnectionName)
