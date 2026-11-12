/*
Azure Container Registry with Private Endpoint Module
------------------------------------------------------
This module creates an Azure Container Registry (Premium SKU) with:
1. Private Endpoint in the specified PE subnet
2. Private DNS Zone (privatelink.azurecr.io) — created or referenced from existing
3. VNet link for the DNS zone
4. DNS Zone Group for the Private Endpoint

Prerequisites:
- Premium SKU is required for Private Endpoint support
- The PE subnet must already exist
*/

@description('Name of the Azure Container Registry')
param acrName string

@description('Azure region for the ACR')
param location string

@description('Resource ID of the Private Endpoint subnet')
param peSubnetId string

@description('Resource ID of the Virtual Network')
param vnetId string

@description('Suffix for unique resource names')
param suffix string

@description('Resource group name for existing ACR DNS zone. Empty string means create a new zone.')
param existingDnsZoneResourceGroup string = ''

@description('Subscription ID where existing private DNS zones are located.')
param dnsZonesSubscriptionId string = subscription().subscriptionId

@description('Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26 or 10.0.0.0/16). When empty, public access remains disabled.')
param developerIpCidr string = ''

@description('Principal ID of the project managed identity to grant AcrPull role. When empty, no role assignment is created.')
param projectPrincipalId string = ''

// ---- ACR Resource ----
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: empty(developerIpCidr) ? 'Disabled' : 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
    networkRuleSet: empty(developerIpCidr) ? null : {
      defaultAction: 'Deny'
      ipRules: [
        {
          action: 'Allow'
          value: developerIpCidr
        }
      ]
    }
  }
}

// ---- Private Endpoint ----
resource acrPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${acrName}-private-endpoint'
  location: location
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: '${acrName}-private-link-service-connection'
        properties: {
          privateLinkServiceId: containerRegistry.id
          groupIds: [ 'registry' ]
        }
      }
    ]
  }
}

// ---- Private DNS Zone ----
var acrDnsZoneName = 'privatelink.azurecr.io'

resource acrPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (empty(existingDnsZoneResourceGroup)) {
  name: acrDnsZoneName
  location: 'global'
}

resource existingAcrPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = if (!empty(existingDnsZoneResourceGroup)) {
  name: acrDnsZoneName
  scope: resourceGroup(dnsZonesSubscriptionId, existingDnsZoneResourceGroup)
}

var acrDnsZoneId = empty(existingDnsZoneResourceGroup) ? acrPrivateDnsZone.id : existingAcrPrivateDnsZone.id

// ---- VNet Link ----
resource acrDnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (empty(existingDnsZoneResourceGroup)) {
  parent: acrPrivateDnsZone
  location: 'global'
  name: 'acr-${suffix}-link'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ---- DNS Zone Group ----
resource acrDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: acrPrivateEndpoint
  name: '${acrName}-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      { name: '${acrName}-dns-config', properties: { privateDnsZoneId: acrDnsZoneId } }
    ]
  }
  dependsOn: [
    empty(existingDnsZoneResourceGroup) ? acrDnsVnetLink : null
  ]
}

// ---- AcrPull Role Assignment ----
// Grants the project managed identity pull access to the ACR
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull built-in role

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(projectPrincipalId)) {
  name: guid(containerRegistry.id, projectPrincipalId, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ---- Outputs ----
@description('Resource ID of the Azure Container Registry')
output acrId string = containerRegistry.id

@description('Name of the Azure Container Registry')
output acrName string = containerRegistry.name

@description('Login server URL of the Azure Container Registry')
output acrLoginServer string = containerRegistry.properties.loginServer
