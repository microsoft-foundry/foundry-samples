param location string
param config object
param deployWorkspace bool = true
param deployComponent bool = true

var createWorkspace = config.logAnalyticsWorkspace.mode == 'create'
module workspace 'workspace.bicep' = if (createWorkspace && deployWorkspace) {
  name: 'foundry-monitor-workspace'
  params: {
    location: location
    name: config.logAnalyticsWorkspace.name
    ingestion: config.publicNetworkAccessForIngestion
    query: config.publicNetworkAccessForQuery
  }
}

var workspaceId = createWorkspace
  ? (deployWorkspace ? workspace!.outputs.resourceId : resourceId('Microsoft.OperationalInsights/workspaces', config.logAnalyticsWorkspace.name))
  : config.logAnalyticsWorkspace.resourceId

resource insights 'Microsoft.Insights/components@2020-02-02' = if (deployComponent) {
  name: config.name
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    publicNetworkAccessForIngestion: config.publicNetworkAccessForIngestion
    publicNetworkAccessForQuery: config.publicNetworkAccessForQuery
  }
}

output resourceId string = resourceId('Microsoft.Insights/components', config.name)
output workspaceResourceId string = workspaceId
