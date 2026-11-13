/*
Basic Agent Setup with VNet Injection - Network Secured
-----------------------------------
This template creates:
  - A virtual network with agent and private endpoint subnets
  - An AI Foundry account with network injection (VNet integration for agents)
  - Private endpoint and DNS zones for the AI Services account
  - An AI Foundry project with system-assigned managed identity
  - A capability host for the project (basic agent, no BYO resources)
  - A model deployment (gpt-4.1 by default)

This is a "basic" agent setup — it does NOT create or connect BYO resources
(Azure AI Search, Storage Account, Cosmos DB). The platform-managed resources
are used instead.
*/
@description('Location for all resources.')
@allowed([
  'australiaeast'
  'brazilsouth'
  'canadacentral'
  'canadaeast'
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
// Uses only resourceGroup().id for determinism — re-deploys target the same resources
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)
var accountName = toLower('${aiServices}${uniqueSuffix}')
var acrName = toLower('acr${uniqueSuffix}')

@description('Name for your project resource.')
param firstProjectName string = 'project'

@description('This project will be a sub-resource of your account')
param projectDescription string = 'A project for the AI Foundry account with network secured basic Agent'

@description('The display name of the project')
param displayName string = 'network secured basic agent project'

// Virtual Network parameters
@description('Virtual Network name for the Agent to create new or existing virtual network')
param vnetName string = 'agent-vnet-test'

@description('The name of Agents Subnet to create new or existing subnet for agents')
param agentSubnetName string = 'agent-subnet'

@description('The name of Private Endpoint subnet to create new or existing subnet for private endpoints')
param peSubnetName string = 'pe-subnet'

@description('Existing Virtual Network name Resource ID')
param existingVnetResourceId string = ''

@description('Address space for the VNet (only used for new VNet)')
param vnetAddressPrefix string = ''

@description('Address prefix for the agent subnet. The default value is 192.168.0.0/24 but you can choose any size /26 or any class like 10.0.0.0 or 172.168.0.0')
param agentSubnetPrefix string = ''

@description('Address prefix for the private endpoint subnet')
param peSubnetPrefix string = ''

@description('Enable Azure Container Registry with Private Endpoint. When true, creates an ACR (Premium SKU) with a PE in the private endpoints subnet.')
param enableContainerRegistry bool = true

@description('Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26 or 10.0.0.0/16). When empty, public access remains disabled.')
param developerIpCidr string = ''

// DNS zone parameters
@description('Subscription ID where existing private DNS zones are located. Leave empty to use current subscription.')
param dnsZonesSubscriptionId string = ''

@description('Object mapping DNS zone names to their resource group, or empty string to indicate creation')
param existingDnsZones object = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''
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
  'privatelink.azurecr.io'
]

@description('The name of the project capability host to be created')
param projectCapHost string = 'caphostproj'


var projectName = toLower('${firstProjectName}${uniqueSuffix}')

// Check if existing VNet has been passed in
var existingVnetPassedIn = existingVnetResourceId != ''

var vnetParts = split(existingVnetResourceId, '/')
var vnetSubscriptionId = existingVnetPassedIn ? vnetParts[2] : subscription().subscriptionId
var vnetResourceGroupName = existingVnetPassedIn ? vnetParts[4] : resourceGroup().name
var existingVnetName = existingVnetPassedIn ? last(vnetParts) : vnetName
var trimVnetName = trim(existingVnetName)

// Resolve DNS zones subscription ID - use current subscription if not specified
var resolvedDnsZonesSubscriptionId = empty(dnsZonesSubscriptionId) ? subscription().subscriptionId : dnsZonesSubscriptionId


/*
  Step 1: Create Virtual Network and Subnets
  - Agent subnet delegated to Microsoft.App/environments for VNet injection
  - Private endpoint subnet for secure access to AI Services
*/
module vnet 'modules-network-secured/network-agent-vnet.bicep' = {
  name: 'vnet-${trimVnetName}-${uniqueSuffix}-deployment'
  params: {
    vnetName: trimVnetName
    useExistingVnet: existingVnetPassedIn
    existingVnetResourceGroupName: vnetResourceGroupName
    agentSubnetName: agentSubnetName
    peSubnetName: peSubnetName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetPrefix: agentSubnetPrefix
    peSubnetPrefix: peSubnetPrefix
    existingVnetSubscriptionId: vnetSubscriptionId
    location: location
  }
}

/*
  Step 2: Create the AI Services account with network injection and model deployment
  - Network injection points the agent subnet for VNet integration
  - Public network access is disabled
  - Model deployment (gpt-4.1 by default)
*/
module aiAccount 'modules-network-secured/ai-account-identity.bicep' = {
  name: '${accountName}-${uniqueSuffix}-deployment'
  params: {
    accountName: accountName
    location: location
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
    agentSubnetId: vnet.outputs.agentSubnetId
  }
}

/*
  Step 3: Private Endpoint and DNS Configuration for AI Services
  - Creates private endpoint in the PE subnet
  - Sets up private DNS zones for AI Services, OpenAI, and Cognitive Services
  - Links DNS zones to the VNet for name resolution
*/
module privateEndpointAndDNS 'modules-network-secured/private-endpoint-and-dns.bicep' = {
  name: '${uniqueSuffix}-private-endpoint'
  params: {
    aiAccountName: aiAccount.outputs.accountName
    vnetName: vnet.outputs.virtualNetworkName
    peSubnetName: vnet.outputs.peSubnetName
    suffix: uniqueSuffix
    vnetResourceGroupName: vnet.outputs.virtualNetworkResourceGroup
    vnetSubscriptionId: vnet.outputs.virtualNetworkSubscriptionId
    existingDnsZones: existingDnsZones
    dnsZonesSubscriptionId: resolvedDnsZonesSubscriptionId
  }
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
    projectPrincipalId: project.identity.principalId
  }
  dependsOn: [
    privateEndpointAndDNS
  ]
}

// Application Insights for hosted-agent tracing (this template ships none). Creates a
// workspace-based Application Insights and connects it to the account so the agent exports traces.
module applicationInsights 'modules-network-secured/application-insights.bicep' = {
  name: 'app-insights-${uniqueSuffix}-deployment'
  params: {
    location: location
    suffix: uniqueSuffix
    aiAccountName: aiAccount.outputs.accountName
    disablePublicIngestion: true
  }
}

// Private trace ingestion path (Azure Monitor Private Link Scope) so an in-VNet agent's traces
// reach Application Insights over the private link rather than the (disabled) public endpoint.
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
  dependsOn: [
    privateEndpointAndDNS
  ]
}

/*
  Step 4: Create a Project
  - Sub-resource of the AI Services account
  - System-assigned managed identity
  - No BYO resource connections (basic agent setup)
*/
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: displayName
  }
  dependsOn: [
    aiAccount
    privateEndpointAndDNS
  ]
}

/*
  Step 5: Create the Capability Host for the project
  - Basic agent capability host (no BYO connections)
  - Platform-managed resources are used for thread storage, file storage, and vector store
*/
module addProjectCapabilityHost 'modules-network-secured/add-project-capability-host.bicep' = {
  name: 'capabilityHost-configuration-${uniqueSuffix}-deployment'
  params: {
    accountName: aiAccount.outputs.accountName
    projectName: projectName
    projectCapHost: projectCapHost
  }
  dependsOn: [
    project
    privateEndpointAndDNS
  ]
}

output accountId string = aiAccount.outputs.accountID
output accountName string = aiAccount.outputs.accountName
output projectName string = project.name
