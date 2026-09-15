targetScope = 'resourceGroup'

// =================================================================================================
// Main parameters
// =================================================================================================

@minLength(1)
@maxLength(64)
@description('Name of the application. Used to ensure resource names are unique.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

// =================================================================================================
// Project module parameters
// =================================================================================================

@description('Name of the Cognitive Services account')
param accountName string = '${environmentName}acct'

@description('Name of the Cognitive Services project')
param projectName string = '${environmentName}proj'

@description('Name of the Container Registry')
param containerRegistryName string = '${environmentName}acr'

@description('SKU of Cognitive Services account')
param cognitiveServicesSku string = 'S0'

@description('Controls public network access for the Foundry account')
@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

@description('Name of the Foundry workload spoke virtual network')
param virtualNetworkName string = '${environmentName}-spoke-vnet'

@description('Address prefix for the Foundry workload spoke virtual network')
param spokeVirtualNetworkAddressPrefix string = '10.0.0.0/16'

@description('Address prefix for the hosted agent subnet')
param agentSubnetAddressPrefix string = '10.0.0.0/24'

@description('Address prefix for the private endpoint subnet')
param privateEndpointSubnetAddressPrefix string = '10.0.1.0/24'

@description('Address prefix for optional workload virtual machines')
param virtualMachineSubnetAddressPrefix string = '10.0.2.0/24'

@description('Name of the hub virtual network')
param hubVirtualNetworkName string = '${environmentName}-hub-vnet'

@description('Address prefix for the hub virtual network')
param hubVirtualNetworkAddressPrefix string = '10.1.0.0/16'

@description('Address prefix for the AzureFirewallSubnet. Must be /26 or larger.')
param azureFirewallSubnetAddressPrefix string = '10.1.0.0/26'

@description('Name of the Azure Firewall')
param firewallName string = '${environmentName}-firewall'

@description('Name of the Azure Firewall policy')
param firewallPolicyName string = '${environmentName}-firewall-policy'

@description('Name of the route table applied to the workload spoke subnets')
param spokeRouteTableName string = '${environmentName}-spoke-route-table'

@description('SKU of Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param containerRegistrySku string = 'Basic'

@description('Name of the Log Analytics workspace')
param logAnalyticsName string = '${environmentName}-logs'

@description('Name of the Application Insights component')
param applicationInsightsName string = '${environmentName}-appi'

param agentName string = '${environmentName}-autopilot-agent'

// =================================================================================================
// Model deployment parameters
// =================================================================================================

@description('Model name')
param modelName string = 'gpt-chat-latest'

@description('Model version')
param modelVersion string = '2026-05-28'

// =================================================================================================
// Common parameters
// =================================================================================================

@description('Tags to apply to all resources')
param tags object = {}

// =================================================================================================
// Module deployments
// =================================================================================================

module publicAccount 'modules/public-account.bicep' = if (publicNetworkAccess == 'Enabled') {
  name: 'public-account-deployment'
  params: {
    accountName: accountName
    location: location
    tags: tags
    cognitiveServicesSku: cognitiveServicesSku
  }
}

module privateNetworking 'modules/private-networking.bicep' = if (publicNetworkAccess == 'Disabled') {
  name: 'private-networking-deployment'
  params: {
    accountName: accountName
    location: location
    tags: tags
    cognitiveServicesSku: cognitiveServicesSku
    virtualNetworkName: virtualNetworkName
    spokeVirtualNetworkAddressPrefix: spokeVirtualNetworkAddressPrefix
    agentSubnetAddressPrefix: agentSubnetAddressPrefix
    privateEndpointSubnetAddressPrefix: privateEndpointSubnetAddressPrefix
    virtualMachineSubnetAddressPrefix: virtualMachineSubnetAddressPrefix
    hubVirtualNetworkName: hubVirtualNetworkName
    hubVirtualNetworkAddressPrefix: hubVirtualNetworkAddressPrefix
    azureFirewallSubnetAddressPrefix: azureFirewallSubnetAddressPrefix
    firewallName: firewallName
    firewallPolicyName: firewallPolicyName
    spokeRouteTableName: spokeRouteTableName
  }
}

module project 'modules/project.bicep' = {
  name: 'project-deployment'
  params: {
    accountName: accountName
    projectName: projectName
    containerRegistryName: containerRegistryName
    location: location
    tags: tags
    cognitiveServicesSku: cognitiveServicesSku
    containerRegistrySku: containerRegistrySku
    modelName: modelName
    modelVersion: modelVersion
    logAnalyticsName: logAnalyticsName
    applicationInsightsName: applicationInsightsName
  }
  dependsOn: [
    publicAccount
    privateNetworking
  ]
}

// =================================================================================================
// Outputs - These become environment variables in post-provision.sh
// =================================================================================================

@description('ACR login server endpoint')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = project.outputs.acrloginServer

output AZURE_AI_PROJECT_ENDPOINT string = project.outputs.foundryProjectEndpoint

output SUBSCRIPTION_ID string = subscription().subscriptionId

output RESOURCE_GROUP string = resourceGroup().name

output LOCATION string = location

output ACCOUNT_NAME string = accountName

output PROJECT_NAME string = projectName

output AGENT_NAME string = agentName

output TENANT_ID string = tenant().tenantId

output PROJECT_PRINCIPAL_ID string = project.outputs.foundryProjectPrincipalId

output MODEL_NAME string = modelName

output PUBLIC_NETWORK_ACCESS string = publicNetworkAccess

output VIRTUAL_NETWORK_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.virtualNetworkId : ''

output HUB_VIRTUAL_NETWORK_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.hubVirtualNetworkId : ''

output AZURE_FIREWALL_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.firewallId : ''

output AZURE_FIREWALL_PRIVATE_IP string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.firewallPrivateIpAddress : ''

output SPOKE_ROUTE_TABLE_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.spokeRouteTableId : ''

output AGENT_SUBNET_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.agentSubnetId : ''

output VIRTUAL_MACHINE_SUBNET_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.virtualMachineSubnetId : ''

output PRIVATE_ENDPOINT_ID string = publicNetworkAccess == 'Disabled' ? privateNetworking!.outputs.privateEndpointId : ''

output APPLICATIONINSIGHTS_CONNECTION_STRING string = project.outputs.applicationInsightsConnectionString

output APPLICATIONINSIGHTS_RESOURCE_ID string = project.outputs.applicationInsightsResourceId
