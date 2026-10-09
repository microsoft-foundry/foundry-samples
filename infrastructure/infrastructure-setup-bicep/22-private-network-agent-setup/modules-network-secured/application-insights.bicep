/*
Application Insights Module
---------------------------
This module creates workspace-based Application Insights for agent tracing with:
1. Log Analytics workspace
2. Application Insights component (private ingestion for network-secured templates)
3. Connection on the Foundry account so agents export OpenTelemetry traces here
*/

@description('Azure region for the tracing resources.')
param location string

@description('Suffix for unique resource names (the template uniqueSuffix).')
param suffix string

@description('Name of the Foundry (AI Services) account to connect Application Insights to.')
param aiAccountName string

@description('When true, disable public ingestion (reach Application Insights privately via AMPLS). Set false for public templates.')
param disablePublicIngestion bool = true

@description('Name of the Log Analytics workspace to create.')
param logAnalyticsName string = 'law-tracing-${suffix}'

@description('Name of the Application Insights component to create.')
param appInsightsName string = 'appi-tracing-${suffix}'

resource aiAccount 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' existing = {
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
    publicNetworkAccessForIngestion: disablePublicIngestion ? 'Disabled' : 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Foundry account connection (category AppInsights) so the agent exports OTel traces here.
resource connection 'Microsoft.CognitiveServices/accounts/connections@2026-05-15-preview' = {
  name: '${aiAccountName}-appinsights'
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

@description('Resource ID of the Application Insights component.')
output appInsightsId string = appInsights.id

@description('Application ID of the Application Insights component (for trace queries).')
output appInsightsAppId string = appInsights.properties.AppId

@description('Resource ID of the Log Analytics workspace backing Application Insights.')
output logAnalyticsId string = logAnalytics.id
