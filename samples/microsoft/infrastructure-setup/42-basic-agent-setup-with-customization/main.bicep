@description('The name of the Azure AI Foundry resource.')
@maxLength(9)
param aiFoundryName string = 'foundy'

@description('The name of your project')
param projectName string = 'project'

@description('The description of your project')
param projectDescription string = 'some description'

@description('The display name of your project')
param projectDisplayName string = 'project_display_name'

@description('The Azure region where your AI Foundry resource and project will be created.')
@allowed([
  'australiaeast'
  'canadaeast'
  'eastus'
  'eastus2'
  'francecentral'
  'japaneast'
  'koreacentral'
  'norwayeast'
  'polandcentral'
  'southindia'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westus'
  'westus3'
  'westeurope'
  'southeastasia'
])
param location string = 'westus'

// Get the existing Azure OpenAI resource
@description('The existing Azure OpenAI resource ID.')
param existingAoaiResourceId string = ''


// Whether to create an App Insights resource
@description('True/False if you want to create an Azure Application Insights resource for the project.')
@allowed([
  true
  false
])
param createAppInsights bool = true

@description('The name of the App Insights resource to create')
param appInsightsName string = 'foundryappinsights'

param azureDeployName string = utcNow()
var accountName string = '${aiFoundryName}${substring(uniqueString(azureDeployName), 0,4)}'

// The name of the connection to the existing Azure OpenAI resource
var byoAoaiConnectionName = 'aoaiConnection'


// get subid, resource group name and resource name from the existing resource id
var existingAoaiResourceIdParts = split(existingAoaiResourceId, '/')
var existingAoaiResourceIdSubId = existingAoaiResourceIdParts[2]
var existingAoaiResourceIdRgName = existingAoaiResourceIdParts[4]
var existingAoaiResourceIdName = existingAoaiResourceIdParts[8]


resource existingAoaiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  scope: resourceGroup(existingAoaiResourceIdSubId, existingAoaiResourceIdRgName)
  name: existingAoaiResourceIdName
}

// Conditionally creates a new App Insights resource
resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (createAppInsights) {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}


// Create a new account resource
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  #disable-next-line use-stable-resource-identifiers
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

// Create a new project, a sub-resource of the account
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectDisplayName
  }

  // Create a project connection to the existing Azure OpenAI resource
  resource byoAoaiConnection 'connections@2025-04-01-preview' = {
    name: byoAoaiConnectionName
    properties: {
      category: 'AzureOpenAI'
      target: existingAoaiResource.properties.endpoint
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: existingAoaiResource.id
        location: existingAoaiResource.location
      }
    }
  }
  
  // Creates the project connection to your Azure App Insights resource
  resource appInsightsConnections 'connections@2025-04-01-preview' = if (createAppInsights) {
    name: appInsightsName
    properties: {
      category: 'AppInsights'
      target: appInsights.id
      authType: 'ApiKey'
      credentials: {
        key: appInsights.properties.ConnectionString
      }
      metadata: {
        ApiType: 'Azure'
        ResourceId: appInsights.id
      }
    }
  }
}



// Set the account capability host
resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  name: '${account.name}-capHost'
  parent: account
  properties: {
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    project
  ]
}

// Set the project capability host
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: '${projectName}-capHost'
  parent: project
  properties: {
    capabilityHostKind: 'Agents'
    aiServicesConnections: ['${byoAoaiConnectionName}']
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output accountName string = account.name
output projectName string = project.name
