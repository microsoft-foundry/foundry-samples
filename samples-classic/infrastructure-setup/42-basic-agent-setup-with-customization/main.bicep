param azureDeployName string = utcNow()

@maxLength(9)
@description('The name of the Azure AI Foundry resource.')
param account_name string = 'foundy'

var accountName string = '${account_name}${substring(uniqueString(azureDeployName), 0,4)}'

@description('The name of your project')
param project_name string = 'project'

@description('The description of your project')
param projectDescription string = 'some description'

@description('The display name of your project')
param projectDisplayName string = 'project_display_name'

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
  'westus2'
  'westus3'
  'westeurope'
  'southeastasia'
  'brazilsouth'
  'germanywestcentral'
  'italynorth'
  'southafricanorth'
  'southcentralus'
])
@description('The Azure region where your AI Foundry resource and project will be created.')
param location string = 'westus'

// TO DO: Update the resource ID to point to an existing Azure OpenAI resource in your subscription
@description('The resource ID of the existing Azure OpenAI resource.')
param existingAoaiResourceId string = ''

var byoAoaiConnectionName = 'aoaiConnection'

// get subid, resource group name and resource name from the existing resource id
var existingAoaiResourceIdParts = split(existingAoaiResourceId, '/')
var existingAoaiResourceIdSubId = existingAoaiResourceIdParts[2]
var existingAoaiResourceIdRgName = existingAoaiResourceIdParts[4]
var existingAoaiResourceIdName = existingAoaiResourceIdParts[8]

// Get the existing Azure OpenAI resource
resource existingAoaiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  scope: resourceGroup(existingAoaiResourceIdSubId, existingAoaiResourceIdRgName)
  name: existingAoaiResourceIdName
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
  name: project_name
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
  name: '${project_name}-capHost'
  parent: project
  properties: {
    capabilityHostKind: 'Agents'
    aiServicesConnections: ['${byoAoaiConnectionName}']
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

output account_endpoint string = account.properties.endpoint
output account_name string = account.name
output project_name string = project.name
