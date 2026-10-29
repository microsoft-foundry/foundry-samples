/*
Standard Setup Network Secured Steps for main.bicep
-----------------------------------
*/
@description('Location for all resources.')
@allowed([
  'westus'
  'eastus'
  'eastus2'
  'eastus2euap'
  'westcentralus'
  'japaneast'
  'francecentral'
  'spaincentral'
  'uaenorth'
  'southcentralus'
  'italynorth'
  'germanywestcentral'
  'brazilsouth'
  'southafricanorth'
  'australiaeast'
  'swedencentral'
  'canadaeast'
  'canadacentral'
  'westeurope'
  'westus3'
  'uksouth'
  'southindia'

  //only class B and C
  'koreacentral'
  'polandcentral'
  'switzerlandnorth'
  'norwayeast'
])
param location string = 'eastus'

@description('Azure region for the tracing resources (Log Analytics workspace + Application Insights). These resource types are not available in every region (e.g. eastus2euap), so they can be pinned to a nearby supported region while the rest of the deployment uses `location`. The AMPLS private endpoint still lands in the VNet region.')
param monitorLocation string = 'eastus2'

@description('Deploy the agent-tracing stack (Application Insights + Log Analytics + Azure Monitor Private Link Scope). Set false to skip it, e.g. in regions where Log Analytics is unavailable or when tracing is not needed for a test.')
param enableTracing bool = true

@description('Name for your AI Services resource.')
param aiServices string = 'aiservices'

// Model deployment parameters
@description('The name of the model you want to deploy')
param modelName string = 'gpt-4.1'
@description('The provider of your model')
param modelFormat string = 'OpenAI'
@description('The version of your model')
param modelVersion string = '2025-04-14'
@description('The sku of your model deployment')
param modelSkuName string = 'GlobalStandard'
@description('The tokens per minute (TPM) of your model deployment')
param modelCapacity int = 30

// Create a short, unique suffix, that will be unique to each resource group
// Deterministic suffix for idempotent re-deploys (same RG = same names)
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)
var accountName = toLower('${aiServices}${uniqueSuffix}')

@description('Name for your project resource.')
param firstProjectName string = 'project'

@description('This project will be a sub-resource of your account')
param projectDescription string = 'A project for the AI Foundry account with network secured deployed Agent'

@description('The display name of the project')
param displayName string = 'network secured agent project'

// Existing Virtual Network parameters
// vnetName precedence + UX clarity.
// When existingVnetResourceId is set, vnetName is IGNORED and the actual name
// is derived from the resource ID (`last(vnetParts)`). The original default
// 'agent-vnet-test' was misleading: users who copied it as-is alongside
// existingVnetResourceId thought they were targeting a specific VNet but the
// resource ID won, hiding mistakes. Default is now empty.
@description('Virtual Network name. Required ONLY when creating a NEW VNet (existingVnetResourceId is empty). When existingVnetResourceId is set, this value is IGNORED, the name is derived from the resource ID. If you supply both they should match; otherwise the resource ID wins.')
param vnetName string = ''

@description('The name of Agents Subnet to create new or existing subnet for agents')
param agentSubnetName string = 'agent-subnet'

@description('The name of Private Endpoint subnet to create new or existing subnet for private endpoints')
param peSubnetName string = 'pe-subnet'

//Existing standard Agent required resources
@description('Existing Virtual Network name Resource ID')
param existingVnetResourceId string = ''

@description('Address space for the VNet (only used for new VNet)')
param vnetAddressPrefix string = ''

@description('Address prefix for the agent subnet. The default value is 192.168.0.0/24 but you can choose any size /26 or any class like 10.0.0.0 or 172.168.0.0')
param agentSubnetPrefix string = ''

@description('Address prefix for the private endpoint subnet')
param peSubnetPrefix string = ''

// Non-destructive subnet handling.
// Set to true when bringing your own pre-configured subnets (NSG/RT/PE policies
// already set by your platform team). Prevents the template from doing a PUT
// that would reset privateEndpointNetworkPolicies and trip tenant policies.
@description('When true and existingVnetResourceId is set, the template will NOT modify your existing subnets.')
param reuseExistingSubnets bool = false

// True BYO Foundry account.
// When set, the template references the existing AI Foundry account instead of
// writing the RG-derived account name. It does not update existing account networking.
@description('Optional existing Foundry AIServices account ID. Reference-only: does not configure network injection, repair the account capability host, or deploy a model. Verify the existing account is already network injected and ready; deploy the project in the account resource group/subscription.')
param existingAiFoundryAccountResourceId string = ''

@description('Skip model deployment for a new account when true. The existing-account branch never creates a model, regardless of this flag; required model deployments must already exist there.')
param skipModelDeployment bool = false

@description('Enable Azure Container Registry with Private Endpoint. When true, creates an ACR (Premium SKU) with a PE in the private endpoints subnet.')
param enableContainerRegistry bool = true

@description('Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26 or 10.0.0.0/16). When empty, public access remains disabled.')
param developerIpCidr string = ''

@description('Create private endpoints and DNS zone groups for AI Search, Storage, and Cosmos DB. Set false only when the supplied existing resources already have private endpoints reachable from this VNet. The Foundry account private endpoint is always created.')
param createDependentResourcePrivateEndpoints bool = true

@description('Assign Cosmos DB Operator and Storage Blob Data Contributor to the Project managed identity. Set false when capabilitySettings provisioning is authorized by the ARM caller; grant these roles to the Project identity after provisioning and before data-plane use.')
param assignProjectStorageAndCosmosAccountRoles bool = true

// Scenario 22: the account-level capability host is ALWAYS implicit. For a fresh
// account it is auto-created by the platform via `networkInjections.scenario='agent'`
// (see ai-account-identity.bicep). This template intentionally has no opt-in
// account capability-host module and no `createAccountCapabilityHost` flag.

@description('The AI Search Service full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param aiSearchResourceId string = ''
@description('The AI Storage Account full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param azureStorageAccountResourceId string = ''
@description('The Cosmos DB Account full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param azureCosmosDBAccountResourceId string = ''

//New Param for resource group of Private DNS zones
//@description('Optional: Resource group containing existing private DNS zones. If specified, DNS zones will not be created.')
//param existingDnsZonesResourceGroup string = ''

@description('Subscription ID where existing private DNS zones are located. Leave empty to use current subscription.')
param dnsZonesSubscriptionId string = ''

@description('Object mapping DNS zone names to their resource group, or empty string to indicate creation')
param existingDnsZones object = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''
  'privatelink.search.windows.net': ''
  'privatelink.blob.core.windows.net': ''
  'privatelink.documents.azure.com': ''
  'privatelink.azurecr.io': ''
}

@description('Object mapping Azure Monitor private DNS zone names to the resource group of an existing zone, or empty string to create it. Use to bring your own centralized Private DNS Zones (e.g. an Azure Landing Zone connectivity subscription) for agent tracing.')
param existingMonitorDnsZones object = {
  'privatelink.monitor.azure.com': ''
  'privatelink.oms.opinsights.azure.com': ''
  'privatelink.ods.opinsights.azure.com': ''
  'privatelink.agentsvc.azure-automation.net': ''
}

@description('Zone Names for Validation of existing Private Dns Zones')
param dnsZoneNames array = [
  'privatelink.services.ai.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.search.windows.net'
  'privatelink.blob.core.windows.net'
  'privatelink.documents.azure.com'
  'privatelink.azurecr.io'
]


var projectName = toLower('${firstProjectName}${uniqueSuffix}')
// Sanitize aiServices for storage account name: lowercase, no hyphens, max 24 chars total.
// Reserve last 6 chars for `${uniqueSuffix}st` so uniqueness is preserved when prefix is truncated.
var aiServicesSanitized = toLower(replace(aiServices, '-', ''))
var storagePrefixMax = 18 // 24 total - 4 (uniqueSuffix) - 2 ('st' marker)
var storagePrefix = length(aiServicesSanitized) > storagePrefixMax
  ? substring(aiServicesSanitized, 0, storagePrefixMax)
  : aiServicesSanitized
var azureStorageName = '${storagePrefix}${uniqueSuffix}st'

// Cosmos DB allows hyphens but enforces 44-char max. Cap defensively.
var cosmosDBNameRaw = toLower('${aiServices}${uniqueSuffix}cosmosdb')
var cosmosDBName = length(cosmosDBNameRaw) > 44 ? substring(cosmosDBNameRaw, 0, 44) : cosmosDBNameRaw

var aiSearchName = toLower('${aiServices}${uniqueSuffix}search')
var acrName = toLower('acr${uniqueSuffix}')

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

// Resolve DNS zones subscription ID - use current subscription if not specified.
// Accept either form: bare GUID or "/subscriptions/<guid>".
// The full ARM path form previously broke the existing-zone cross-sub references
// silently (the subscriptionId field needs the bare GUID).
var normalizedDnsZonesSubscriptionId = empty(dnsZonesSubscriptionId)
  ? ''
  : (startsWith(toLower(dnsZonesSubscriptionId), '/subscriptions/')
      ? split(dnsZonesSubscriptionId, '/')[2]
      : dnsZonesSubscriptionId)
var resolvedDnsZonesSubscriptionId = empty(normalizedDnsZonesSubscriptionId) ? subscription().subscriptionId : normalizedDnsZonesSubscriptionId

// Scenario 22: the network-injected parent enables implicit host provisioning;
// the project's capabilitySettings selects its BYO stores. No projectCapHost name
// or explicit host module is declared. The service does not create RBAC assignments.

@description('Deploy Project MI runtime grants by default: Storage Blob Data Owner at storage-account scope with the module ABAC condition, and Cosmos DB Built-in Data Contributor on the enterprise_memory database. Set false only when equivalent runtime grants are explicitly managed outside this deployment. The service does not create RBAC assignments.')
param assignContainerRoles bool = true

// Create Virtual Network and Subnets
module vnet 'modules-network-secured/network-agent-vnet.bicep' = {
  name: 'vnet-${trimVnetName}-${uniqueSuffix}-deployment'
  params: {
    location: location
    vnetName: trimVnetName
    useExistingVnet: existingVnetPassedIn
    existingVnetResourceGroupName: vnetResourceGroupName
    agentSubnetName: agentSubnetName
    peSubnetName: peSubnetName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetPrefix: agentSubnetPrefix
    peSubnetPrefix: peSubnetPrefix
    existingVnetSubscriptionId: vnetSubscriptionId
    reuseExistingSubnets: reuseExistingSubnets
  }
}

/*
  Create the AI Services account and gpt-4o model deployment
*/
module aiAccount 'modules-network-secured/ai-account-identity.bicep' = {
  name: '${accountName}-${uniqueSuffix}-deployment'
  params: {
    // workspace organization
    accountName: accountName
    location: location
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
    agentSubnetId: vnet.outputs.agentSubnetId
    existingAccountResourceId: existingAiFoundryAccountResourceId
    skipModelDeployment: skipModelDeployment
  }
}
/*
  Validate existing resources
  This module will check if the AI Search Service, Storage Account, and Cosmos DB Account already exist.
  If they do, it will set the corresponding output to true. If they do not exist, it will set the output to false.
*/
module validateExistingResources 'modules-network-secured/validate-existing-resources.bicep' = {
  name: 'validate-existing-resources-${uniqueSuffix}-deployment'
  params: {
    aiSearchResourceId: aiSearchResourceId
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureCosmosDBAccountResourceId: azureCosmosDBAccountResourceId
    existingDnsZones: existingDnsZones
    dnsZoneNames: dnsZoneNames
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
  }
}

// Fail fast when a bring-your-own AI Search service rejects Microsoft Entra
// (AAD) data-plane auth (apiKeyOnly). Foundry's CognitiveSearch connection uses
// authType=AAD, so an unpatched existing service leaves agents failing with 403.
// Only the existing-service path needs this; a service this template creates is
// already configured for AAD.
module validateSearchAadAuth 'modules-network-secured/validate-search-aad-auth.bicep' = if (searchPassedIn) {
  name: 'validate-search-aad-auth-${uniqueSuffix}-deployment'
  params: {
    aiSearchName: last(acsParts)
    aiSearchResourceGroupName: aiSearchServiceResourceGroupName
    aiSearchSubscriptionId: aiSearchServiceSubscriptionId
  }
}

// This module will create new agent dependent resources
// A Cosmos DB account, an AI Search Service, and a Storage Account are created if they do not already exist
module aiDependencies 'modules-network-secured/standard-dependent-resources.bicep' = {
  name: 'dependencies-${uniqueSuffix}-deployment'
  params: {
    location: location
    azureStorageName: azureStorageName
    aiSearchName: aiSearchName
    cosmosDBName: cosmosDBName

    // AI Search Service parameters
    aiSearchResourceId: aiSearchResourceId
    aiSearchExists: validateExistingResources.outputs.aiSearchExists

    // Storage Account
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureStorageExists: validateExistingResources.outputs.azureStorageExists

    // Cosmos DB Account
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

// Private Endpoint and DNS Configuration
// This module sets up private network access for all Azure services:
// 1. Creates private endpoints in the specified subnet
// 2. Sets up private DNS zones for each service
// 3. Links private DNS zones to the VNet for name resolution
// 4. Configures network policies to restrict access to private endpoints only
module privateEndpointAndDNS 'modules-network-secured/private-endpoint-and-dns.bicep' = {
    name: '${uniqueSuffix}-private-endpoint'
    params: {
      aiAccountName: aiAccount.outputs.accountName    // AI Services to secure
      aiSearchName: aiDependencies.outputs.aiSearchName       // AI Search to secure
      storageName: aiDependencies.outputs.azureStorageName        // Storage to secure
      cosmosDBName:aiDependencies.outputs.cosmosDBName
      vnetName: vnet.outputs.virtualNetworkName    // VNet containing subnets
      peSubnetName: vnet.outputs.peSubnetName        // Subnet for private endpoints
      suffix: uniqueSuffix                                    // Unique identifier
      vnetResourceGroupName: vnet.outputs.virtualNetworkResourceGroup
      vnetSubscriptionId: vnet.outputs.virtualNetworkSubscriptionId // Subscription ID for the VNet
      cosmosDBSubscriptionId: cosmosDBSubscriptionId // Subscription ID for Cosmos DB
      cosmosDBResourceGroupName: cosmosDBResourceGroupName // Resource Group for Cosmos DB
      aiSearchSubscriptionId: aiSearchServiceSubscriptionId // Subscription ID for AI Search Service
      aiSearchResourceGroupName: aiSearchServiceResourceGroupName // Resource Group for AI Search Service
      storageAccountResourceGroupName: azureStorageResourceGroupName // Resource Group for Storage Account
      storageAccountSubscriptionId: azureStorageSubscriptionId // Subscription ID for Storage Account
      existingDnsZones: existingDnsZones
      dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
      createDependentResourcePrivateEndpoints: createDependentResourcePrivateEndpoints
    }
    dependsOn: [
    aiSearch      // Ensure AI Search exists
    storage       // Ensure Storage exists
    cosmosDB      // Ensure Cosmos DB exists
  ]
  }

// Optional: Azure Container Registry with Private Endpoint
module acr 'modules-network-secured/container-registry.bicep' = if (enableContainerRegistry) {
  name: 'acr-${uniqueSuffix}-deployment'
  params: {
    acrName: acrName
    location: location
    peSubnetId: vnet.outputs.peSubnetId
    vnetId: vnet.outputs.virtualNetworkId
    suffix: uniqueSuffix
    existingDnsZoneResourceGroup: existingDnsZones['privatelink.azurecr.io']
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
    developerIpCidr: developerIpCidr
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

// Optional Application Insights for agent tracing. Creates a
// workspace-based Application Insights and connects it to the account so the agent exports traces.
module applicationInsights 'modules-network-secured/application-insights.bicep' = if (enableTracing) {
  name: 'app-insights-${uniqueSuffix}-deployment'
  params: {
    // Log Analytics / App Insights are not available in eastus2euap, so they use monitorLocation.
    location: monitorLocation
    suffix: uniqueSuffix
    aiAccountName: aiAccount.outputs.accountName
    disablePublicIngestion: true
  }
}

// Private trace ingestion path (Azure Monitor Private Link Scope) so an in-VNet agent's traces
// reach Application Insights over the private link rather than the (disabled) public endpoint.
module monitorPrivateLink 'modules-network-secured/monitor-private-link-scope.bicep' = if (enableTracing) {
  name: 'monitor-pls-${uniqueSuffix}-deployment'
  params: {
    location: location
    suffix: uniqueSuffix
    appInsightsId: applicationInsights.outputs.appInsightsId
    logAnalyticsId: applicationInsights.outputs.logAnalyticsId
    vnetId: vnet.outputs.virtualNetworkId
    peSubnetId: vnet.outputs.peSubnetId
    existingDnsZones: existingMonitorDnsZones
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

/*
  Creates a new project (sub-resource of the AI Services account)
*/
module aiProject 'modules-network-secured/ai-project-identity.bicep' = {
  name: '${projectName}-${uniqueSuffix}-deployment'
  params: {
    // workspace organization
    projectName: projectName
    projectDescription: projectDescription
    displayName: displayName
    location: location

    aiSearchName: aiDependencies.outputs.aiSearchName
    aiSearchServiceResourceGroupName: aiDependencies.outputs.aiSearchServiceResourceGroupName
    aiSearchServiceSubscriptionId: aiDependencies.outputs.aiSearchServiceSubscriptionId

    cosmosDBName: aiDependencies.outputs.cosmosDBName
    cosmosDBSubscriptionId: aiDependencies.outputs.cosmosDBSubscriptionId
    cosmosDBResourceGroupName: aiDependencies.outputs.cosmosDBResourceGroupName

    azureStorageName: aiDependencies.outputs.azureStorageName
    azureStorageSubscriptionId: aiDependencies.outputs.azureStorageSubscriptionId
    azureStorageResourceGroupName: aiDependencies.outputs.azureStorageResourceGroupName
    // dependent resources
    accountName: aiAccount.outputs.accountName
  }
  dependsOn: [
     validateSearchAadAuth
     privateEndpointAndDNS
     cosmosDB
     aiSearch
     storage
  ]
}

module formatProjectWorkspaceId 'modules-network-secured/format-project-workspace-id.bicep' = {
  name: 'format-project-workspace-id-${uniqueSuffix}-deployment'
  params: {
    projectWorkspaceId: aiProject.outputs.projectWorkspaceId
  }
}

/*
  Assigns the project SMI the storage blob data contributor role on the storage account
*/
module storageAccountRoleAssignment 'modules-network-secured/azure-storage-account-role-assignment.bicep' = if (assignProjectStorageAndCosmosAccountRoles) {
  name: 'storage-${azureStorageName}-${uniqueSuffix}-deployment'
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

// Explicit Project MI grant. This module depends on the Project output and cannot
// authorize its earlier implicit provisioning; arrange caller permissions first.
module cosmosAccountRoleAssignments 'modules-network-secured/cosmosdb-account-role-assignment.bicep' = if (assignProjectStorageAndCosmosAccountRoles) {
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

// Explicit Project MI runtime grants; independent host readiness must be checked.
module aiSearchRoleAssignments 'modules-network-secured/ai-search-role-assignments.bicep' = {
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

// Scenario 22: network injection enables implicit account/project hosts, with
// project capabilitySettings supplying store IDs. The service creates no RBAC.
// These Bicep modules assign Project MI roles under the deployment identity.
// Caller provisioning permissions must already exist; disabled modules leave
// their runtime grants to an authorized operator. File order is not a host barrier.

// Bicep deploys these runtime grants by default. Storage uses account scope with
// an ABAC condition; Cosmos uses database scope. The modules do not pre-create
// containers, and implicit container creation never supplies role assignments.
module storageContainersRoleAssignment 'modules-network-secured/blob-storage-container-role-assignments.bicep' = if (assignContainerRoles) {
  name: 'storage-containers-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
  params: {
    aiProjectPrincipalId: aiProject.outputs.projectPrincipalId
    storageName: aiDependencies.outputs.azureStorageName
    workspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
  }
  dependsOn: [
    storageAccountRoleAssignment
  ]
}

module cosmosContainerRoleAssignments 'modules-network-secured/cosmos-container-role-assignments.bicep' = if (assignContainerRoles) {
  name: 'cosmos-containers-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosAccountName: aiDependencies.outputs.cosmosDBName
    projectWorkspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    cosmosAccountRoleAssignments
    storageContainersRoleAssignment
  ]
}
