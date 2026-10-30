param location string
param vnetId string
param subnetId string
param targetId string
param peName string
param groupId string
param zones array
param deployEndpoint bool
param deployZoneGroup bool
param existingEndpointResourceId string = ''

resource dnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in zones: if (zone.deployZone) {
  name: zone.name
  location: 'global'
}]
resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for zone in zones: if (zone.deployLink) {
  name: '${zone.name}/evaluation'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
  dependsOn: [
    dnsZones
  ]
}]
resource endpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (deployEndpoint) {
  name: peName
  location: location
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: peName
        properties: {
          privateLinkServiceId: targetId
          groupIds: [groupId]
        }
      }
    ]
  }
}
resource zoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (deployZoneGroup) {
  name: '${peName}/default'
  properties: {
    privateDnsZoneConfigs: [for zone in zones: {
      name: replace(zone.name, '.', '-')
      properties: {
        privateDnsZoneId: zone.resourceId
      }
    }]
  }
  dependsOn: [
    endpoint
    links
  ]
}

output endpointResourceId string = empty(existingEndpointResourceId) ? resourceId('Microsoft.Network/privateEndpoints', peName) : existingEndpointResourceId
