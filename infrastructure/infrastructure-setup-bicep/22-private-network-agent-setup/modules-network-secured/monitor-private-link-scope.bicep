/*
Azure Monitor Private Link Scope (AMPLS) Module
-----------------------------------------------
This module enables private trace ingestion to Application Insights with:
1. Azure Monitor Private Link Scope (PrivateOnly ingestion, Open query)
2. Application Insights and Log Analytics added as scoped resources
3. Azure Monitor private DNS zones linked to the VNet
4. Private Endpoint (azuremonitor) in the PE subnet with a DNS zone group
*/

@description('Azure region for the private endpoint.')
param location string

@description('Suffix for unique resource names (the template uniqueSuffix).')
param suffix string

@description('Resource ID of the Application Insights component to scope into the AMPLS.')
param appInsightsId string

@description('Resource ID of the Log Analytics workspace to scope into the AMPLS.')
param logAnalyticsId string

@description('Resource ID of the Virtual Network.')
param vnetId string

@description('Resource ID of the Private Endpoint subnet.')
param peSubnetId string

@description('Map of Azure Monitor private DNS zone name to the resource group of an existing zone. An empty string for a zone means the module creates and links it in this resource group; a non-empty resource group means bring your own existing (e.g. centralized Azure Landing Zone) zone, which is referenced instead of recreated.')
param existingDnsZones object = {
  'privatelink.monitor.azure.com': ''
  'privatelink.oms.opinsights.azure.com': ''
  'privatelink.ods.opinsights.azure.com': ''
  'privatelink.agentsvc.azure-automation.net': ''
}

@description('Subscription ID where existing Azure Monitor private DNS zones are located. Defaults to the current subscription.')
param dnsZonesSubscriptionId string = subscription().subscriptionId

// Azure Monitor private DNS zones. Blob zone omitted: the standard templates already create + link it for BYO storage.
var monitorDnsZoneNames = [
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
  'privatelink.agentsvc.azure-automation.net'
]

// 1. Azure Monitor Private Link Scope (private ingestion, open query).
resource ampls 'Microsoft.Insights/privateLinkScopes@2021-07-01-preview' = {
  name: 'ampls-tracing-${suffix}'
  location: 'global'
  properties: {
    accessModeSettings: {
      ingestionAccessMode: 'PrivateOnly'
      queryAccessMode: 'Open'
    }
  }
}

// 2. Scope the Application Insights component and its Log Analytics workspace.
resource amplsAppInsights 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'appinsights-scoped'
  properties: {
    linkedResourceId: appInsightsId
  }
}

resource amplsLogAnalytics 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'law-scoped'
  properties: {
    linkedResourceId: logAnalyticsId
  }
}

// 3. The Azure Monitor private DNS zones. Zones are created and linked to the VNet only when
// not supplied via existingDnsZones; bring-your-own (centralized) zones are referenced as-is and
// are neither recreated nor relinked here, matching the ALZ centralized Private DNS Zone model.
resource monitorDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in monitorDnsZoneNames: if (empty(existingDnsZones[zone])) {
  name: zone
  location: 'global'
}]

resource monitorDnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [for (zone, i) in monitorDnsZoneNames: if (empty(existingDnsZones[zone])) {
  parent: monitorDnsZones[i]
  name: '${replace(zone, '.', '-')}-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    registrationEnabled: false
  }
}]

// Resolve each zone's resource ID: a newly created zone lives in this resource group, while a
// bring-your-own zone is referenced in its (optionally cross-subscription) resource group.
var monitorDnsZoneIds = [for zone in monitorDnsZoneNames: empty(existingDnsZones[zone])
  ? resourceId('Microsoft.Network/privateDnsZones', zone)
  : extensionResourceId(format('/subscriptions/{0}/resourceGroups/{1}', dnsZonesSubscriptionId, existingDnsZones[zone]), 'Microsoft.Network/privateDnsZones', zone)]

// 4. Private endpoint to the AMPLS (group 'azuremonitor') + DNS zone group.
resource amplsPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'ampls-tracing-${suffix}-pe'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'ampls-connection'
        properties: {
          privateLinkServiceId: ampls.id
          groupIds: [
            'azuremonitor'
          ]
        }
      }
    ]
  }
  dependsOn: [
    amplsAppInsights
    amplsLogAnalytics
  ]
}

resource amplsDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: amplsPrivateEndpoint
  name: 'ampls-dns'
  properties: {
    privateDnsZoneConfigs: [for (zone, i) in monitorDnsZoneNames: {
      name: replace(zone, '.', '-')
      properties: {
        privateDnsZoneId: monitorDnsZoneIds[i]
      }
    }]
  }
  dependsOn: [
    monitorDnsZoneLinks
  ]
}

@description('Resource ID of the Azure Monitor Private Link Scope.')
output amplsId string = ampls.id
