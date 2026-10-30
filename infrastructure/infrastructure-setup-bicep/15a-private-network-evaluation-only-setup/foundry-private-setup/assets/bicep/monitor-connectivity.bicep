param location string
param vnetId string
param subnetId string
param scopeId string
param deployScope bool
param insightsId string
param workspaceId string
param deployInsightsAssociation bool
param deployWorkspaceAssociation bool
param peName string
param zones array
param deployEndpoint bool
param deployZoneGroup bool
param existingEndpointResourceId string = ''

var scopeParts = split(scopeId, '/')
module monitorScope 'monitor-scope.bicep' = {
  name: 'foundry-monitor-scope'
  scope: resourceGroup(scopeParts[2], scopeParts[4])
  params: {
    name: scopeParts[8]
    deployScope: deployScope
    insightsId: insightsId
    workspaceId: workspaceId
    deployInsightsAssociation: deployInsightsAssociation
    deployWorkspaceAssociation: deployWorkspaceAssociation
  }
}
module network 'connectivity.bicep' = {
  name: 'foundry-monitor-network'
  params: {
    location: location
    vnetId: vnetId
    subnetId: subnetId
    targetId: monitorScope.outputs.resourceId
    peName: peName
    groupId: 'azuremonitor'
    zones: zones
    deployEndpoint: deployEndpoint
    deployZoneGroup: deployZoneGroup
    existingEndpointResourceId: existingEndpointResourceId
  }
}

output endpointResourceId string = network.outputs.endpointResourceId
