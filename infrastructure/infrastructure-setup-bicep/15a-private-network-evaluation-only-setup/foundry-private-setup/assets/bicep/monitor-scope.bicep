param name string
param deployScope bool
param insightsId string
param workspaceId string
param deployInsightsAssociation bool
param deployWorkspaceAssociation bool

resource ampls 'Microsoft.Insights/privateLinkScopes@2021-07-01-preview' = if (deployScope) {
  name: name
  location: 'global'
  properties: {
    accessModeSettings: {
      ingestionAccessMode: 'PrivateOnly'
      queryAccessMode: 'PrivateOnly'
    }
  }
}
resource insights 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = if (deployInsightsAssociation) {
  name: '${name}/insights'
  properties: {
    linkedResourceId: insightsId
  }
  dependsOn: [
    ampls
  ]
}
resource workspace 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = if (deployWorkspaceAssociation) {
  name: '${name}/workspace'
  properties: {
    linkedResourceId: workspaceId
  }
  dependsOn: [
    ampls
  ]
}

output resourceId string = resourceId('Microsoft.Insights/privateLinkScopes', name)
