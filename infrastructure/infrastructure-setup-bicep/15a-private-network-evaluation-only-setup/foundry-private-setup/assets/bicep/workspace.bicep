param location string
param name string
param ingestion string
param query string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: ingestion
    publicNetworkAccessForQuery: query
  }
}

output resourceId string = workspace.id
