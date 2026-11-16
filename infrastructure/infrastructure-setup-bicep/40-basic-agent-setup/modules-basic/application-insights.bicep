/*
Application Insights Module (public)

Creates workspace-based Application Insights for agent tracing: Log Analytics workspace, App Insights
component (public ingestion), and a Foundry account connection so agents export OpenTelemetry traces.
Evaluation reads these traces back.
*/

@description('Azure region for the tracing resources (new resources only).')
param location string

@description('Name of the Foundry (AI Services) account to connect Application Insights to.')
param aiAccountName string

@description('Name of the Log Analytics workspace to create.')
param logAnalyticsName string

@description('Name of the Application Insights component to create.')
param appInsightsName string

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiAccountName
  scope: resourceGroup()
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Foundry account connection (category AppInsights) so the agent exports OTel traces here.
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: 'appinsights'
  parent: aiAccount
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

@description('Name of the Application Insights component.')
output appInsightsName string = appInsights.name

@description('Resource ID of the Application Insights component.')
output appInsightsId string = appInsights.id

@description('Application ID of the Application Insights component (for trace queries).')
output appInsightsAppId string = appInsights.properties.AppId

@description('Resource ID of the Log Analytics workspace backing Application Insights.')
output logAnalyticsId string = logAnalytics.id
