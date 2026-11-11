targetScope = 'resourceGroup'

@description('Name of the existing Foundry account in THIS deployment resource group.')
param accountName string

@description('Name of the existing project under accountName. The project must have a system-assigned managed identity.')
param projectName string

@description('Resource ID of the existing target Foundry account hosting the model. May be in another resource group or subscription in the same tenant.')
param targetAccountResourceId string

@description('Target Foundry OpenAI base URL, including /openai/v1 and no trailing slash. Use the actual endpoint, not the target ARM resource ID.')
param targetOpenAIBaseUrl string

@description('Existing model deployment name on the target account, not the underlying catalog model name.')
param modelDeploymentName string

@description('Project connection name. Agents reference <connectionName>/<modelDeploymentName>.')
param connectionName string = 'foundry-models'

@description('Grant Foundry User on the target account to the source PROJECT managed identity. Requires roleAssignments/write at the target account and deployment permissions in its resource group. Set false only if access is already provisioned.')
param assignBackendRole bool = true

@description('Cognitive Services token audience for the target cloud. The default is for AzureCloud.')
param audience string = 'https://cognitiveservices.azure.com'

@description('Foundry data-plane hostname suffix for the source cloud. Used only for the project endpoint output; the default is for AzureCloud.')
param foundryDataPlaneSuffix string = 'services.ai.azure.com'

var targetIdParts = split(targetAccountResourceId, '/')
var targetAccountName = targetIdParts[8]
var targetSubscriptionId = targetIdParts[2]
var targetResourceGroupName = targetIdParts[4]
var discoveryBaseUrl = replace(targetOpenAIBaseUrl, '/openai/v1', '/openai')

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

module projectModelRole 'modules/project-model-role.bicep' = if (assignBackendRole) {
  name: 'foundry-model-role-${uniqueString(project.id, connectionName, targetAccountResourceId)}'
  scope: resourceGroup(targetSubscriptionId, targetResourceGroupName)
  params: {
    targetAccountName: targetAccountName
    projectPrincipalId: project.identity.principalId
  }
}

// ApiManagement is the connection category; no API Management service is deployed.
resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: connectionName
  properties: {
    category: 'ApiManagement'
    target: targetOpenAIBaseUrl
    // The service supports PMI; the published Bicep authType enum does not yet include it.
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    audience: audience
    credentials: {}
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: targetAccountResourceId
      displayName: connectionName
      upstreamSurface: 'responses'
      deploymentInPath: 'false'
      deploymentAPIVersion: '2022-12-01'
      customHeaders: '{}'
      models: '[]'
      modelDiscovery: string({
        listModelsEndpoint: '${discoveryBaseUrl}/deployments'
        getModelEndpoint: '${discoveryBaseUrl}/deployments/{deploymentName}'
        deploymentProvider: 'OpenAI'
      })
    }
  }
  dependsOn: [
    projectModelRole
  ]
}

output connectionId string = connection.id
output connectionName string = connection.name
output modelReference string = '${connectionName}/${modelDeploymentName}'
output projectEndpoint string = 'https://${account.properties.customSubDomainName}.${foundryDataPlaneSuffix}/api/projects/${projectName}'
output targetEndpoint string = targetOpenAIBaseUrl
output roleAssignmentId string = assignBackendRole ? projectModelRole!.outputs.roleAssignmentId : ''
