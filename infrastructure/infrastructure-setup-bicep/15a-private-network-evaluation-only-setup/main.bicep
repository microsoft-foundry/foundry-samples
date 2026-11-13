/*
Evaluation-Only Network Secured Setup - main.bicep
-----------------------------------
A simplified private-network setup for evaluation and data-generation scenarios.
This template does NOT deploy Cosmos DB or AI Search.
It deploys the AI Services account, a project with a storage connection,
a VNet with private endpoints, workspace-based Application Insights (with private
ingestion via Azure Monitor Private Link Scope) for evaluation/agent tracing, and
an optional project-level capability host for data-generation workloads that
use the hosted-agent runtime.
*/
@description('Location for all resources.')
@allowed([
  'australiaeast'
  'brazilsouth'
  'westeurope'
  'canadaeast'
  'canadacentral'
  'centralindia'
  'centralus'
  'eastasia'
  'eastus'
  'francecentral'
  'germanywestcentral'
  'italynorth'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'northeurope'
  'norwayeast'
  'qatarcentral'
  'southafricanorth'
  'southcentralus'
  'southindia'
  'southeastasia'
  'spaincentral'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westeurope'
  'westus'
  'westus3'
  'usgovarizona'
  'usgovvirginia'
])
param location string = any(resourceGroup().location)

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
param projectDescription string = 'A project for the AI Foundry account with network secured evaluation setup'

@description('The display name of the project')
param displayName string = 'network secured evaluation project'

// Existing Virtual Network parameters
@description('Virtual Network name for the Agent to create new or existing virtual network')
param vnetName string = 'agent-vnet-test'

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

@description('The AI Storage Account full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param azureStorageAccountResourceId string = ''

@description('Enable Azure Container Registry with Private Endpoint. When true, creates an ACR (Premium SKU) with a PE in the private endpoints subnet.')
param enableContainerRegistry bool = true

@description('Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26 or 10.0.0.0/16). When empty, public access remains disabled.')
param developerIpCidr string = ''

@description('Subscription ID where existing private DNS zones are located. Leave empty to use current subscription.')
param dnsZonesSubscriptionId string = ''

@description('Object mapping DNS zone names to their resource group, or empty string to indicate creation')
param existingDnsZones object = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''
  'privatelink.blob.core.windows.net': ''
  'privatelink.azurecr.io': ''
}

@description('Zone Names for Validation of existing Private Dns Zones')
param dnsZoneNames array = [
  'privatelink.services.ai.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.blob.core.windows.net'
  'privatelink.azurecr.io'
]

@description('Object mapping Azure Monitor private DNS zone names to the resource group of an existing zone, or empty string to create it. Use to bring your own centralized Private DNS Zones (e.g. an Azure Landing Zone connectivity subscription) for evaluation/agent tracing.')
param existingMonitorDnsZones object = {
  'privatelink.monitor.azure.com': ''
  'privatelink.oms.opinsights.azure.com': ''
  'privatelink.ods.opinsights.azure.com': ''
  'privatelink.agentsvc.azure-automation.net': ''
}

@description('Deploy the project-level capability host (Agents kind, no BYO connections). Required for data-generation workloads that use the hosted-agent runtime; not needed for evaluation-only.')
param deployCapabilityHost bool = true

@description('The name of the project capability host to be created.')
param projectCapHost string = 'caphostproj'


var projectName = toLower('${firstProjectName}${uniqueSuffix}')
var azureStorageName = toLower('${aiServices}${uniqueSuffix}storage')
var acrName = toLower('acr${uniqueSuffix}')

// Check if existing resources have been passed in
var storagePassedIn = azureStorageAccountResourceId != ''
var existingVnetPassedIn = existingVnetResourceId != ''

var storageParts = split(azureStorageAccountResourceId, '/')
var azureStorageSubscriptionId = storagePassedIn ? storageParts[2] : subscription().subscriptionId
var azureStorageResourceGroupName = storagePassedIn ? storageParts[4] : resourceGroup().name

var vnetParts = split(existingVnetResourceId, '/')
var vnetSubscriptionId = existingVnetPassedIn ? vnetParts[2] : subscription().subscriptionId
var vnetResourceGroupName = existingVnetPassedIn ? vnetParts[4] : resourceGroup().name
var existingVnetName = existingVnetPassedIn ? last(vnetParts) : vnetName
var trimVnetName = trim(existingVnetName)

// Resolve DNS zones subscription ID - use current subscription if not specified
var resolvedDnsZonesSubscriptionId = empty(dnsZonesSubscriptionId) ? subscription().subscriptionId : dnsZonesSubscriptionId

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
  }
}

/*
  Create the AI Services account and model deployment
*/
module aiAccount 'modules-network-secured/ai-account-identity.bicep' = {
  name: '${accountName}-${uniqueSuffix}-deployment'
  params: {
    accountName: accountName
    location: resourceGroup().location
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
    agentSubnetId: vnet.outputs.agentSubnetId
  }
}

/*
  Validate existing resources
  This module will check if the Storage Account already exists.
*/
module validateExistingResources 'modules-network-secured/validate-existing-resources.bicep' = {
  name: 'validate-existing-resources-${uniqueSuffix}-deployment'
  params: {
    azureStorageAccountResourceId: azureStorageAccountResourceId
    existingDnsZones: existingDnsZones
    dnsZoneNames: dnsZoneNames
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
  }
}

// This module will create a new Storage Account if one does not already exist
module aiDependencies 'modules-network-secured/standard-dependent-resources.bicep' = {
  name: 'dependencies-${uniqueSuffix}-deployment'
  params: {
    location: location
    azureStorageName: azureStorageName

    // Storage Account
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureStorageExists: validateExistingResources.outputs.azureStorageExists
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: aiDependencies.outputs.azureStorageName
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
}

// Private Endpoint and DNS Configuration
// This module sets up private network access for AI Services and Storage:
// 1. Creates private endpoints in the specified subnet
// 2. Sets up private DNS zones for each service
// 3. Links private DNS zones to the VNet for name resolution
module privateEndpointAndDNS 'modules-network-secured/private-endpoint-and-dns.bicep' = {
  name: '${uniqueSuffix}-private-endpoint'
  params: {
    aiAccountName: aiAccount.outputs.accountName
    location: location                               // Co-locate PEs with target resources (issue #657)
    storageName: aiDependencies.outputs.azureStorageName
    vnetName: vnet.outputs.virtualNetworkName
    peSubnetName: vnet.outputs.peSubnetName
    suffix: uniqueSuffix
    vnetResourceGroupName: vnet.outputs.virtualNetworkResourceGroup
    vnetSubscriptionId: vnet.outputs.virtualNetworkSubscriptionId
    storageAccountResourceGroupName: azureStorageResourceGroupName
    storageAccountSubscriptionId: azureStorageSubscriptionId
    existingDnsZones: existingDnsZones
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
  }
  dependsOn: [
    storage
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

/*
  Creates a new project (sub-resource of the AI Services account)
*/
module aiProject 'modules-network-secured/ai-project-identity.bicep' = {
  name: '${projectName}-${uniqueSuffix}-deployment'
  params: {
    projectName: projectName
    projectDescription: projectDescription
    displayName: displayName
    location: location

    azureStorageName: aiDependencies.outputs.azureStorageName
    azureStorageSubscriptionId: aiDependencies.outputs.azureStorageSubscriptionId
    azureStorageResourceGroupName: aiDependencies.outputs.azureStorageResourceGroupName

    accountName: aiAccount.outputs.accountName
  }
  dependsOn: [
    privateEndpointAndDNS
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
module storageAccountRoleAssignment 'modules-network-secured/azure-storage-account-role-assignment.bicep' = {
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

/*
  Assigns the project SMI the Foundry User role on the AI Services account
*/
module aiAccountRoleAssignment 'modules-network-secured/ai-account-role-assignment.bicep' = {
  name: 'ai-account-ra-${uniqueSuffix}-deployment'
  params: {
    accountName: aiAccount.outputs.accountName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

// The Storage Blob Data Owner role assignment
module storageContainersRoleAssignment 'modules-network-secured/blob-storage-container-role-assignments.bicep' = {
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

/*
  Application Insights for evaluation and agent tracing (this template ships none by default).
  Creates a workspace-based Application Insights and connects it to the account so evaluation
  runs and agents export metrics/results/OpenTelemetry traces here.
*/
module applicationInsights 'modules-network-secured/application-insights.bicep' = {
  name: 'app-insights-${uniqueSuffix}-deployment'
  params: {
    location: location
    suffix: uniqueSuffix
    aiAccountName: aiAccount.outputs.accountName
    disablePublicIngestion: true
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

/*
  Private trace ingestion path (Azure Monitor Private Link Scope) so ingestion to Application
  Insights stays on the private link rather than the (disabled) public endpoint.
*/
module monitorPrivateLink 'modules-network-secured/monitor-private-link-scope.bicep' = {
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
}

/*
  Grant the project managed identity read access on the Application Insights resource so
  evaluation can query GenAI trace content back.
*/
module applicationInsightsRoleAssignment 'modules-network-secured/application-insights-role-assignment.bicep' = {
  name: 'app-insights-ra-${uniqueSuffix}-deployment'
  params: {
    appInsightsName: applicationInsights.outputs.appInsightsName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

/*
  Optional project-level capability host for data-generation workloads.
  The account-level capability host is auto-created via the account's
  networkInjections.scenario='agent' (see ai-account-identity.bicep), so only the
  project caphost is created here. No BYO connections (no Cosmos DB / AI Search / storage backend).
  The dependsOn entries are ordering-only: they run the project caphost after the
  account and project are fully configured, giving the platform time to finish
  auto-creating the account capability host before the project host binds to it.
*/
module addProjectCapabilityHost 'modules-network-secured/add-project-capability-host.bicep' = if (deployCapabilityHost) {
  name: 'capabilityHost-configuration-${uniqueSuffix}-deployment'
  params: {
    accountName: aiAccount.outputs.accountName
    projectName: aiProject.outputs.projectName
    projectCapHost: projectCapHost
  }
  dependsOn: [
    privateEndpointAndDNS
    aiAccountRoleAssignment
    applicationInsightsRoleAssignment
  ]
}
