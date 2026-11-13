/*
  ================================================================================
  ai-gateway-tier-private — self-contained network-secured AI Gateway tier (Path B)
  --------------------------------------------------------------------------------
  One-shot deployment: stands up the full template 16 (private-network standard
  agent) foundation AND the AI Gateway tier layer in a single deployment, so there
  is no "deploy template 16 first" step. Mirrors the self-contained re-author
  pattern of the sibling byom-cross-region extension: it references the shared
  ../../modules-network-secured/* modules and inlines the orchestration.

  What it deploys (all in one region):

    Foundation (template 16 standard network-secured agent):
      - VNet with agent + private-endpoint subnets.
      - Private AI Foundry account + project (publicNetworkAccess Disabled).
      - Cosmos DB, AI Search, Storage (private endpoints + private DNS).
      - The project capability host (agent runtime).

    AI Gateway tier layer:
      - A private hub Foundry account (publicNetworkAccess Disabled) + model + a
        private endpoint into the pe-subnet (reusing the cognitive DNS zones the
        foundation creates).
      - An apim-outbound subnet (delegated Microsoft.Web/serverFarms, NSG) on the VNet.
      - The AI Gateway tier instance (Microsoft.ApiManagement/service, AIGateway
        SKU) with INBOUND-PUBLIC + OUTBOUND-PRIVATE networking: virtualNetworkType
        'External' + outbound virtualNetworkConfiguration into the delegated subnet,
        publicNetworkAccess 'Enabled'. This mirrors the StandardV2 byom-cross-region
        posture: the gateway endpoint stays reachable by the managed Agent Service
        inference plane, while the gateway reaches the private hub account over the
        VNet. A fully-private gateway (publicNetworkAccess Disabled + inbound PE) is
        NOT used because connected-model calls originate from the managed inference
        plane, not the delegated agent subnet.
      - The Foundry model provider (managed-identity import), a gateway model with a
        token-limit policy, a runtime key, and the gateway MI's Foundry User role.
      - The ModelGateway "Admin-connected models" connection on the project, so an
        agent references the model as <connectionName>/<modelName>.

  Single region: the AIGateway SKU is release-gated, and outbound integration
  requires the VNet in the SAME region, so the whole sample deploys in Sweden
  Central. The region parameter is
  named `region` (not `location`) so generic tooling that rewrites `location`
  cannot relocate an AIGateway sample out of its supported regions.

  The AIGateway networking property shapes (virtualNetworkType /
  virtualNetworkConfiguration / publicNetworkAccess) are verified against the live
  AIGateway SKU; the type emits BCP081 (no types available) so they can't be
  validated at build time — keep these exact values.

  Verified against:
    https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking
    https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway
  ================================================================================
*/

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Region — single region for the whole sample (foundation + hub + gateway).
// Named `region` (not `location`) so generic tooling that rewrites `location`
// cannot relocate an AIGateway sample out of its supported regions.
// ---------------------------------------------------------------------------
@allowed([
  'swedencentral'
])
@description('Region for resources that require the AI Gateway tier and its co-regional VNet.')
param region string = 'swedencentral'

// ===========================================================================
// Foundation inputs (template 16 standard network-secured agent)
// ===========================================================================
@description('Base name for the AI Services (Foundry) account. A short unique suffix is appended.')
param aiServices string = 'aiservices'

@description('Name for your project resource (base name; a short unique suffix is appended).')
param firstProjectName string = 'project'

@description('Description applied to the project.')
param projectDescription string = 'A project for the AI Foundry account with network secured deployed Agent'

@description('Display name for the project.')
param displayName string = 'network secured agent project'

// ----- Model (shared by the consumer account deployment and the private hub) -----
@description('Model to deploy. The consumer account and the private hub both deploy this model; the gateway imports the hub deployment and callers reference it by this name.')
param modelName string = 'gpt-5.4'

@description('Model format. Example: OpenAI.')
param modelFormat string = 'OpenAI'

@description('Model version. Ensure this version is available in your region.')
param modelVersion string = '2026-03-05'

@description('Model deployment SKU name. Example: GlobalStandard.')
param modelSkuName string = 'GlobalStandard'

@description('Model deployment capacity in thousands of TPM. Set a value your subscription has quota for.')
param modelCapacity int = 1

// ----- Virtual network -----
@description('Virtual Network name (created new, or the name of an existing VNet when existingVnetResourceId is set).')
param vnetName string = 'agent-vnet-test'

@description('Name of the agent delegated subnet.')
param agentSubnetName string = 'agent-subnet'

@description('Name of the private-endpoint subnet.')
param peSubnetName string = 'pe-subnet'

@description('Resource ID of an EXISTING Virtual Network to reuse. Leave empty to create a new VNet.')
param existingVnetResourceId string = ''

@description('Address space for the VNet (only used for a new VNet).')
param vnetAddressPrefix string = ''

@description('Address prefix for the agent subnet (only used for a new VNet).')
param agentSubnetPrefix string = ''

@description('Address prefix for the private endpoint subnet (only used for a new VNet).')
param peSubnetPrefix string = ''

// ----- Optional reuse of existing dependent resources -----
@description('The AI Search Service full ARM Resource ID. Optional; if empty the resource is created.')
param aiSearchResourceId string = ''

@description('The AI Storage Account full ARM Resource ID. Optional; if empty the resource is created.')
param azureStorageAccountResourceId string = ''

@description('The Cosmos DB Account full ARM Resource ID. Optional; if empty the resource is created.')
param azureCosmosDBAccountResourceId string = ''

@description('The API Management Service full ARM Resource ID. Optional; only used to secure an existing API Management with a private endpoint. Leave empty for this sample (the AI Gateway tier instance below is created separately).')
param apiManagementResourceId string = ''

@description('Object mapping DNS zone names to their resource group, or empty string to indicate creation.')
param existingDnsZones object = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''
  'privatelink.search.windows.net': ''
  'privatelink.blob.core.windows.net': ''
  'privatelink.documents.azure.com': ''
  'privatelink.azure-api.net': ''
  'privatelink.azurecr.io': ''
}

@description('Zone names for validation of existing Private DNS zones.')
param dnsZoneNames array = [
  'privatelink.services.ai.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.search.windows.net'
  'privatelink.blob.core.windows.net'
  'privatelink.documents.azure.com'
  'privatelink.azure-api.net'
  'privatelink.azurecr.io'
]

@description('The name of the project capability host to be created.')
param projectCapHost string = 'caphostproj'

// ===========================================================================
// AI Gateway tier layer inputs
// ===========================================================================
@description('Name for the outbound integration subnet added to the VNet for the AI Gateway tier.')
param apimOutboundSubnetName string = 'apim-outbound'

@description('CIDR for the outbound integration subnet. Must be a free /27 (or larger) inside the VNet address space. The default VNet uses 192.168.0.0/24 and 192.168.1.0/24, so 192.168.2.0/27 is free by default.')
param apimOutboundSubnetPrefix string = '192.168.2.0/27'

@description('Base name for the private hub Foundry account (the model backend behind the gateway). A short unique suffix is appended.')
@maxLength(40)
param hubAccountName string = 'aigwhub'

@description('Globally unique AI Gateway name. Resolves to <name>.azure-api.net. Leave empty to auto-generate.')
param gatewayName string = ''

@description('Publisher email required by the API Management service at create time.')
param publisherEmail string = 'noreply@example.com'

@description('Publisher organization name required by the API Management service at create time.')
param publisherName string = 'AI Gateway tier hub (private)'

@description('Tokens-per-minute budget enforced on the model by the gateway token-limit policy (per caller identity). Low by default so the token-limit policy is easy to test (visible HTTP 429 throttling).')
param tokensPerMinute int = 100

@description('Connection name. Callers reference the model as <connectionName>/<modelName>.')
param connectionName string = 'ai-gateway'

@description('HTTP header the connection uses to send the gateway key. The AI Gateway tier authenticates the api-key header.')
param authHeaderName string = 'api-key'

@description('If true, the connection is visible to every project on the account and appears in the Foundry portal "Admin-connected models" picker.')
param isSharedToAll bool = true

// ===========================================================================
// Naming + parsed inputs (mirrors template 16)
// ===========================================================================
// Deterministic suffix for idempotent re-deploys (same RG = same names).
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)
var accountName = toLower('${aiServices}${uniqueSuffix}')
var projectName = toLower('${firstProjectName}${uniqueSuffix}')
var cosmosDBName = toLower('${aiServices}${uniqueSuffix}cosmosdb')
var aiSearchName = toLower('${aiServices}${uniqueSuffix}search')
var azureStorageName = toLower('${aiServices}${uniqueSuffix}storage')

// Check if existing resources have been passed in
var storagePassedIn = azureStorageAccountResourceId != ''
var searchPassedIn = aiSearchResourceId != ''
var cosmosPassedIn = azureCosmosDBAccountResourceId != ''
var existingVnetPassedIn = existingVnetResourceId != ''

var acsParts = split(aiSearchResourceId, '/')
var aiSearchServiceSubscriptionId = searchPassedIn ? acsParts[2] : subscription().subscriptionId
var aiSearchServiceResourceGroupName = searchPassedIn ? acsParts[4] : resourceGroup().name

var cosmosParts = split(azureCosmosDBAccountResourceId, '/')
var cosmosDBSubscriptionId = cosmosPassedIn ? cosmosParts[2] : subscription().subscriptionId
var cosmosDBResourceGroupName = cosmosPassedIn ? cosmosParts[4] : resourceGroup().name

var storageParts = split(azureStorageAccountResourceId, '/')
var azureStorageSubscriptionId = storagePassedIn ? storageParts[2] : subscription().subscriptionId
var azureStorageResourceGroupName = storagePassedIn ? storageParts[4] : resourceGroup().name

var vnetParts = split(existingVnetResourceId, '/')
var vnetSubscriptionId = existingVnetPassedIn ? vnetParts[2] : subscription().subscriptionId
var vnetResourceGroupName = existingVnetPassedIn ? vnetParts[4] : resourceGroup().name
var existingVnetName = existingVnetPassedIn ? last(vnetParts) : vnetName
var trimVnetName = trim(existingVnetName)

// AI Gateway tier naming
var hubName = toLower('${hubAccountName}${uniqueSuffix}')
var effectiveGatewayName = empty(gatewayName) ? 'aigwp${uniqueSuffix}' : gatewayName
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// ===========================================================================
// Foundation — network-secured standard agent (template 16 modules)
// ===========================================================================

// Create Virtual Network and Subnets
module vnet '../../modules-network-secured/network-agent-vnet.bicep' = {
  name: 'vnet-${trimVnetName}-${uniqueSuffix}-deployment'
  params: {
    location: region
    vnetName: trimVnetName
    useExistingVnet: existingVnetPassedIn
    existingVnetResourceGroupName: vnetResourceGroupName
    agentSubnetName: agentSubnetName
    peSubnetName: peSubnetName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetPrefix: agentSubnetPrefix
    peSubnetPrefix: peSubnetPrefix
    existingVnetSubscriptionId: vnetSubscriptionId
  }
}

// Create the consumer AI Services account and its model deployment
module aiAccount '../../modules-network-secured/ai-account-identity.bicep' = {
  name: 'ai-${accountName}-${uniqueSuffix}-deployment'
  params: {
    accountName: accountName
    location: region
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
    agentSubnetId: vnet.outputs.agentSubnetId
  }
}

// Validate existing dependent resources (AI Search, Storage, Cosmos DB, API Management)
module validateExistingResources '../../modules-network-secured/validate-existing-resources.bicep' = {
  name: 'validate-existing-resources-${uniqueSuffix}-deployment'
  params: {
    aiSearchResourceId: aiSearchResourceId
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureCosmosDBAccountResourceId: azureCosmosDBAccountResourceId
    apiManagementResourceId: apiManagementResourceId
    existingDnsZones: existingDnsZones
    dnsZoneNames: dnsZoneNames
  }
}

// Create the agent dependent resources (Cosmos DB, AI Search, Storage) if they do not exist
module aiDependencies '../../modules-network-secured/standard-dependent-resources.bicep' = {
  name: 'dependencies-${uniqueSuffix}-deployment'
  params: {
    location: region
    azureStorageName: azureStorageName
    aiSearchName: aiSearchName
    cosmosDBName: cosmosDBName

    aiSearchResourceId: aiSearchResourceId
    aiSearchExists: validateExistingResources.outputs.aiSearchExists

    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureStorageExists: validateExistingResources.outputs.azureStorageExists

    cosmosDBResourceId: azureCosmosDBAccountResourceId
    cosmosDBExists: validateExistingResources.outputs.cosmosDBExists
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: aiDependencies.outputs.azureStorageName
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
}

resource aiSearch 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: aiDependencies.outputs.aiSearchName
  scope: resourceGroup(aiDependencies.outputs.aiSearchServiceSubscriptionId, aiDependencies.outputs.aiSearchServiceResourceGroupName)
}

resource cosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: aiDependencies.outputs.cosmosDBName
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
}

// Private endpoints + private DNS for the account and dependent resources
module privateEndpointAndDNS '../../modules-network-secured/private-endpoint-and-dns.bicep' = {
  name: '${uniqueSuffix}-private-endpoint'
  params: {
    aiAccountName: aiAccount.outputs.accountName
    aiSearchName: aiDependencies.outputs.aiSearchName
    storageName: aiDependencies.outputs.azureStorageName
    cosmosDBName: aiDependencies.outputs.cosmosDBName
    apiManagementName: validateExistingResources.outputs.apiManagementName
    vnetName: vnet.outputs.virtualNetworkName
    peSubnetName: vnet.outputs.peSubnetName
    // Private endpoints must be co-regional with the VNet (region), not the resource group, which may differ (e.g. the CI deploys into a westus RG).
    privateEndpointLocation: region
    suffix: uniqueSuffix
    vnetResourceGroupName: vnet.outputs.virtualNetworkResourceGroup
    vnetSubscriptionId: vnet.outputs.virtualNetworkSubscriptionId
    cosmosDBSubscriptionId: cosmosDBSubscriptionId
    cosmosDBResourceGroupName: cosmosDBResourceGroupName
    aiSearchSubscriptionId: aiSearchServiceSubscriptionId
    aiSearchResourceGroupName: aiSearchServiceResourceGroupName
    storageAccountResourceGroupName: azureStorageResourceGroupName
    storageAccountSubscriptionId: azureStorageSubscriptionId
    apiManagementResourceGroupName: validateExistingResources.outputs.apiManagementResourceGroupName
    apiManagementSubscriptionId: validateExistingResources.outputs.apiManagementSubscriptionId
    existingDnsZones: existingDnsZones
  }
  dependsOn: [
    aiSearch
    storage
    cosmosDB
  ]
}

// Create the project (sub-resource of the AI Services account)
module aiProject '../../modules-network-secured/ai-project-identity.bicep' = {
  name: 'ai-${projectName}-${uniqueSuffix}-deployment'
  params: {
    projectName: projectName
    projectDescription: projectDescription
    displayName: displayName
    location: region

    aiSearchName: aiDependencies.outputs.aiSearchName
    aiSearchServiceResourceGroupName: aiDependencies.outputs.aiSearchServiceResourceGroupName
    aiSearchServiceSubscriptionId: aiDependencies.outputs.aiSearchServiceSubscriptionId

    cosmosDBName: aiDependencies.outputs.cosmosDBName
    cosmosDBSubscriptionId: aiDependencies.outputs.cosmosDBSubscriptionId
    cosmosDBResourceGroupName: aiDependencies.outputs.cosmosDBResourceGroupName

    azureStorageName: aiDependencies.outputs.azureStorageName
    azureStorageSubscriptionId: aiDependencies.outputs.azureStorageSubscriptionId
    azureStorageResourceGroupName: aiDependencies.outputs.azureStorageResourceGroupName

    accountName: aiAccount.outputs.accountName
  }
  dependsOn: [
    privateEndpointAndDNS
    cosmosDB
    aiSearch
    storage
  ]
}

module formatProjectWorkspaceId '../../modules-network-secured/format-project-workspace-id.bicep' = {
  name: 'format-project-workspace-id-${uniqueSuffix}-deployment'
  params: {
    projectWorkspaceId: aiProject.outputs.projectWorkspaceId
  }
}

// Assign the project SMI the Storage Blob Data Contributor role on the storage account
module storageAccountRoleAssignment '../../modules-network-secured/azure-storage-account-role-assignment.bicep' = {
  name: 'storage-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
  params: {
    azureStorageName: aiDependencies.outputs.azureStorageName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    storage
    privateEndpointAndDNS
  ]
}

// The Cosmos DB Operator role must be assigned before the caphost is created
module cosmosAccountRoleAssignments '../../modules-network-secured/cosmosdb-account-role-assignment.bicep' = {
  name: 'cosmos-account-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosDBName: aiDependencies.outputs.cosmosDBName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    cosmosDB
    privateEndpointAndDNS
  ]
}

// This role can be assigned before or after the caphost is created
module aiSearchRoleAssignments '../../modules-network-secured/ai-search-role-assignments.bicep' = {
  name: 'ai-search-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(aiSearchServiceSubscriptionId, aiSearchServiceResourceGroupName)
  params: {
    aiSearchName: aiDependencies.outputs.aiSearchName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    aiSearch
    privateEndpointAndDNS
  ]
}

// Create the capability host for the project and account
module addProjectCapabilityHost '../../modules-network-secured/add-project-capability-host.bicep' = {
  name: 'capabilityHost-configuration-${uniqueSuffix}-deployment'
  params: {
    accountName: aiAccount.outputs.accountName
    projectName: aiProject.outputs.projectName
    cosmosDBConnection: aiProject.outputs.cosmosDBConnection
    azureStorageConnection: aiProject.outputs.azureStorageConnection
    aiSearchConnection: aiProject.outputs.aiSearchConnection
    projectCapHost: projectCapHost
  }
  dependsOn: [
    aiSearch
    storage
    cosmosDB
    privateEndpointAndDNS
    cosmosAccountRoleAssignments
    storageAccountRoleAssignment
    aiSearchRoleAssignments
  ]
}

// The Storage Blob Data Owner role must be assigned after the caphost is created
module storageContainersRoleAssignment '../../modules-network-secured/blob-storage-container-role-assignments.bicep' = {
  name: 'storage-containers-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
  params: {
    aiProjectPrincipalId: aiProject.outputs.projectPrincipalId
    storageName: aiDependencies.outputs.azureStorageName
    workspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}

// The Cosmos Built-In Data Contributor role must be assigned after the caphost is created
module cosmosContainerRoleAssignments '../../modules-network-secured/cosmos-container-role-assignments.bicep' = {
  name: 'cosmos-container-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosAccountName: aiDependencies.outputs.cosmosDBName
    projectWorkspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    addProjectCapabilityHost
    storageContainersRoleAssignment
  ]
}

// ===========================================================================
// Existing (foundation-created) VNet + cognitive private DNS zones, referenced
// by the AI Gateway tier layer below.
// ===========================================================================
resource cognitiveServicesDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.cognitiveservices.azure.com'
}

resource openAiDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.openai.azure.com'
}

resource servicesAiDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.services.ai.azure.com'
}

// ===========================================================================
// Outbound integration subnet — delegated to Microsoft.Web/serverFarms, with an
// associated NSG. The AIGateway SKU REQUIRES an NSG on the integration subnet
// (deploy fails NetworkSecurityGroupNotFound otherwise); the rules allow the
// outbound 443 to Storage + Key Vault that the gateway uses during integration.
// defaultOutboundAccess false: the platform brokers egress; also satisfies
// guardrails requiring no default outbound.
// ===========================================================================
resource apimOutboundNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'aigw-outbound-nsg-${uniqueSuffix}'
  location: region
  properties: {
    securityRules: [
      {
        name: 'AllowOutboundHttpsToStorage'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Storage'
        }
      }
      {
        name: 'AllowOutboundHttpsToKeyVault'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureKeyVault'
        }
      }
    ]
  }
}

// Added as a standalone subnet resource (name '<vnet>/<subnet>') because the VNet
// is produced by a module in this same deployment. Serialized AFTER the whole
// foundation (vnet + privateEndpointAndDNS): a standalone subnet PUT is a VNet
// write, and the foundation's private-endpoint creation also writes the VNet
// (it disables network policies on the pe-subnet), so running them concurrently
// would fail with AnotherOperationInProgress on the VNet.
resource apimOutboundSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  name: '${trimVnetName}/${apimOutboundSubnetName}'
  properties: {
    addressPrefix: apimOutboundSubnetPrefix
    defaultOutboundAccess: false
    networkSecurityGroup: {
      id: apimOutboundNsg.id
    }
    delegations: [
      {
        name: 'Microsoft.Web/serverFarms'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
  dependsOn: [
    vnet
    privateEndpointAndDNS
  ]
}

// ===========================================================================
// Private hub Foundry account (model backend) — publicNetworkAccess Disabled,
// keyless, reached only through its private endpoint.
// ===========================================================================
resource hubAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: hubName
  location: region
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: false
    customSubDomainName: hubName
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
      bypass: 'AzureServices'
    }
  }
}

resource hubModel 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: hubAccount
  name: modelName
  sku: {
    capacity: modelCapacity
    name: modelSkuName
  }
  properties: {
    model: {
      name: modelName
      format: modelFormat
      version: modelVersion
    }
  }
}

// Private endpoint into the hub account, wired to the foundation's DNS zones.
resource hubAccountPe 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'aigw-hub-account-pe-${uniqueSuffix}'
  location: region
  // dependsOn hubModel: an accounts/deployments PUT flips the account to 'Accepted'
  // transiently, which fails a concurrent PE with AccountProvisioningStateInvalid.
  // dependsOn privateEndpointAndDNS: this PE lands in the shared pe-subnet, and
  // creating it concurrently with the foundation's private endpoints would contend
  // on the subnet write (AnotherOperationInProgress); serialize it after them.
  dependsOn: [
    hubModel
    privateEndpointAndDNS
  ]
  properties: {
    subnet: {
      id: vnet.outputs.peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'aigw-hub-account-pe-${uniqueSuffix}'
        properties: {
          privateLinkServiceId: hubAccount.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource hubAccountPeDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: hubAccountPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink-cognitiveservices'
        properties: {
          privateDnsZoneId: cognitiveServicesDnsZone.id
        }
      }
      {
        name: 'privatelink-openai'
        properties: {
          privateDnsZoneId: openAiDnsZone.id
        }
      }
      {
        name: 'privatelink-services-ai'
        properties: {
          privateDnsZoneId: servicesAiDnsZone.id
        }
      }
    ]
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

// ===========================================================================
// AI Gateway tier instance — inbound-public + outbound-private.
// virtualNetworkType/virtualNetworkConfiguration/publicNetworkAccess are the
// verified AIGateway networking shape (untyped: BCP081).
// ===========================================================================
var foundryEndpoint = endsWith(hubAccount.properties.endpoint, '/') ? hubAccount.properties.endpoint : '${hubAccount.properties.endpoint}/'

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: effectiveGatewayName
  location: region
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'AIGateway'
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    virtualNetworkType: 'External'
    virtualNetworkConfiguration: {
      subnetResourceId: apimOutboundSubnet.id
    }
    publicNetworkAccess: 'Enabled'
  }
}

// Grant the gateway's managed identity Foundry User on the hub account (keyless backend).
resource foundryUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: hubAccount
  name: guid(hubAccount.id, aiGateway.id, foundryUserRoleId)
  properties: {
    principalId: aiGateway.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
  }
}

// The AIGateway SKU auto-creates a 'default' workspace that holds providers/models.
resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

// Foundry model provider — imports the private hub account over managed identity.
resource foundryProvider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: 'foundry'
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry'
    foundry: {
      endpoint: foundryEndpoint
      resourceIds: [
        hubAccount.id
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
  dependsOn: [
    foundryUserRole
    hubModel
    hubAccountPeDns
  ]
}

// Register the deployment as a gateway model, with a token-limit policy.
resource gatewayModel 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: modelName
  properties: {
    displayName: modelName
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: hubModel.id
      modelName: hubModel.name
      modelVersion: modelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokensPerMinute
        counterKey: 'Identity'
      }
    ]
  }
}

// A runtime access key that the connection sends in the api-key header.
resource runtimeKey 'Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: 'default'
  properties: {
    displayName: 'AI Gateway tier hub runtime key'
  }
}

// ===========================================================================
// "Admin-connected models" connection on the (self-created) project.
// Key read via listSecrets in the same deployment (no manual key step).
// ===========================================================================
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

var gatewayModelsBaseUrl = '${aiGateway.properties.gatewayUrl}/default/models/openai/v1'
var staticModels = [
  {
    name: modelName
    properties: {
      model: {
        name: modelName
        version: modelVersion
        format: modelFormat
      }
    }
  }
]

resource gatewayConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: connectionName
  properties: {
    category: 'ModelGateway'
    target: gatewayModelsBaseUrl
    authType: 'ApiKey'
    isSharedToAll: isSharedToAll
    credentials: {
      key: runtimeKey.listSecrets().primaryKey
    }
    metadata: {
      models: string(staticModels)
      deploymentInPath: 'false'
      authHeaderName: authHeaderName
      authHeaderFormat: '{api_key}'
      customHeaders: '{}'
    }
  }
  dependsOn: [
    gatewayModel
    addProjectCapabilityHost
  ]
}

// ===========================================================================
// Outputs
// ===========================================================================
output accountName string = aiAccount.outputs.accountName
output projectName string = aiProject.outputs.projectName
output projectEndpoint string = 'https://${aiAccount.outputs.accountName}.services.ai.azure.com/api/projects/${aiProject.outputs.projectName}'
output hubAccountName string = hubAccount.name
output gatewayName string = aiGateway.name
output gatewayModelsBaseUrl string = gatewayModelsBaseUrl
output connectionName string = gatewayConnection.name
output modelReference string = '${connectionName}/${modelName}'
