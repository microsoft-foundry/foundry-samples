targetScope = 'subscription'

param environmentName string
@minLength(1)
param location string
param modelName string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'
param serviceManagementReference string = ''

var suffix = toLower(uniqueString(subscription().id, environmentName))
var groupName = 'rg-blueprint-greeting-${environmentName}'
var accountName = 'ai${suffix}'
var projectName = 'greeting-${environmentName}'
var appName = 'greeting-mcp-${suffix}'
var endpoint = 'https://${appName}.azurewebsites.net/runtime/webhooks/mcp'
var tags = {
  'azd-env-name': environmentName
  sample: 'blueprint-signin-on-behalf-of-user'
}

resource group 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: groupName
  location: location
  tags: tags
}

module foundation 'foundry.bicep' = {
  name: 'foundry'
  scope: group
  params: {
    location: location
    accountName: accountName
    projectName: projectName
    modelName: modelName
    modelVersion: modelVersion
    tags: tags
  }
}

module entra 'entra.bicep' = {
  name: 'entra'
  scope: group
  params: {
    uniqueName: 'greeting-mcp-${suffix}'
    serviceManagementReference: serviceManagementReference
  }
}

var resourceUri = 'api://${entra.outputs.applicationId}'
var scope = '${resourceUri}/Greeting.Read'

module functionApp 'function.bicep' = {
  name: 'mcp-function'
  scope: group
  params: {
    name: appName
    location: location
    tenantId: tenant().tenantId
    applicationId: entra.outputs.applicationId
    tags: tags
  }
}

module connection 'connection.bicep' = {
  name: 'mcp-connection'
  scope: group
  params: {
    accountName: foundation.outputs.accountName
    projectName: foundation.outputs.projectName
    endpoint: endpoint
    scope: scope
  }
}

output AZURE_AI_ACCOUNT_NAME string = foundation.outputs.accountName
output AZURE_AI_PROJECT_NAME string = foundation.outputs.projectName
output AZURE_AI_PROJECT_ENDPOINT string = foundation.outputs.projectEndpoint
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = foundation.outputs.modelDeployment
output AZURE_RESOURCE_GROUP string = group.name
output AZURE_TENANT_ID string = tenant().tenantId
output MCP_FUNCTION_APP_NAME string = functionApp.outputs.name
output MCP_ENDPOINT string = endpoint
output MCP_API_APPLICATION_ID string = entra.outputs.applicationId
output MCP_API_APPLICATION_OBJECT_ID string = entra.outputs.applicationObjectId
output MCP_API_SCOPE_ID string = entra.outputs.scopeId
output GREETING_CLIENT_ID string = entra.outputs.clientId
output GREETING_CLIENT_OBJECT_ID string = entra.outputs.clientObjectId
output MCP_SCOPE_URI string = scope
output MCP_RESOURCE_URI string = resourceUri
output MCP_CONNECTION_NAME string = connection.outputs.name
