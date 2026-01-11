@description('')
param azureDeployName string = utcNow()
param account_name string = 'aiServices${substring(uniqueString(azureDeployName), 0,4)}'
param project_name string = 'project'
param projectDescription string = 'some description'
param projectDisplayName string = 'project_display_name'
param location string

@description('The resource ID of the existing Azure OpenAI resource.')
param existingAoaiResourceId string

var byoAoaiConnectionName = 'aoaiConnection'

// get subid, resource group name and resource name from the existing resource id
var existingAoaiResourceIdParts = split(existingAoaiResourceId, '/')
var existingAoaiResourceIdSubId = existingAoaiResourceIdParts[2]
var existingAoaiResourceIdRgName = existingAoaiResourceIdParts[4]
var existingAoaiResourceIdName = existingAoaiResourceIdParts[8]

// define the existing Azure OpenAI resource
resource existingAoaiResource 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  scope: resourceGroup(existingAoaiResourceIdSubId, existingAoaiResourceIdRgName)
  name: existingAoaiResourceIdName
}

resource account_name_resource 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  #disable-next-line use-stable-resource-identifiers
  name: account_name
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
    customSubDomainName: account_name
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource account_name_project_name 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account_name_resource
  name: project_name
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectDisplayName
  }

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


resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  name: '${account_name_resource.name}-capHost'
  parent: account_name_resource
  properties: {
    capabilityHostKind: 'Agents'
  }
}

resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: '${project_name}-capHost'
  parent: account_name_project_name
  properties: {
    capabilityHostKind: 'Agents'
    aiServicesConnections: [byoAoaiConnectionName]
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

output ENDPOINT string = account_name_resource.properties.endpoint
output project_name string = account_name_project_name.name
output account_name string = account_name_resource.name
