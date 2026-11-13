targetScope = 'subscription'

// =================================================================================================
// Main parameters
// =================================================================================================

@description('Foundry project name supplied by the microsoft.foundry provider. Kept for provider parameter compatibility.')
#disable-next-line no-unused-params
param foundryProjectName string

@minLength(1)
@maxLength(64)
@description('Name of the application. Used to ensure resource names are unique.')
param environmentName string = replace(resourceGroupName, 'rg-', '')

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Principal ID supplied by the microsoft.foundry provider. Kept for provider parameter compatibility.')
#disable-next-line no-unused-params
param principalId string = ''

@description('Resource group name supplied by the microsoft.foundry provider. Kept for provider parameter compatibility.')
param resourceGroupName string

@description('Resource token salt supplied by the microsoft.foundry provider. Kept for provider parameter compatibility.')
#disable-next-line no-unused-params
param resourceTokenSalt string = ''

// =================================================================================================
// Project module parameters
// =================================================================================================

@description('Name of the Cognitive Services account')
param accountName string = '${environmentName}acct'

@description('Name of the Cognitive Services project')
param projectName string = '${environmentName}proj'

@description('Name of the Container Registry')
param containerRegistryName string = '${environmentName}acr'

@description('SKU of Cognitive Services account')
param cognitiveServicesSku string = 'S0'

@description('SKU of Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param containerRegistrySku string = 'Basic'

param agentName string = '${environmentName}-autopilot-agent'

// =================================================================================================
// Model deployment parameters
// =================================================================================================

@description('Deploy a model in the Foundry account created by this sample. Defaults to false to avoid unexpected cost and quota usage.')
param deployModel bool = false

@description('Existing Responses API endpoint used when deployModel is false.')
param existingModelResponsesEndpoint string = ''

@minLength(1)
@description('Model deployment name. Used for either the new or existing deployment.')
param modelDeploymentName string = 'gpt-5-mini'

@minLength(1)
@description('Model name used when deployModel is true.')
param modelName string = 'gpt-5-mini'

@minLength(1)
@description('Model version used when deployModel is true.')
param modelVersion string = '2025-08-07'

@minLength(1)
@description('Model deployment SKU used when deployModel is true.')
param modelSkuName string = 'GlobalStandard'

@minValue(1)
@description('Model deployment capacity used when deployModel is true.')
param modelCapacity int = 10

// =================================================================================================
// Common parameters
// =================================================================================================

@description('Tags to apply to all resources')
param tags object = {}

// =================================================================================================
// Resource group
// =================================================================================================

resource targetResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// =================================================================================================
// Module deployments
// =================================================================================================

// 1. Deploy the project module (Cognitive Services account, project, and Container Registry)
module project 'modules/project.bicep' = {
  name: 'project-deployment'
  scope: targetResourceGroup
  params: {
    accountName: accountName
    projectName: projectName
    containerRegistryName: containerRegistryName
    location: location
    tags: tags
    cognitiveServicesSku: cognitiveServicesSku
    containerRegistrySku: containerRegistrySku
    deployModel: deployModel
    modelDeploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
  }
}

// =================================================================================================
// Outputs - These become environment variables in post-provision.sh
// =================================================================================================

@description('ACR login server endpoint')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = project.outputs.acrloginServer

output FOUNDRY_PROJECT_ENDPOINT string = project.outputs.foundryProjectEndpoint

output AZURE_AI_PROJECT_ID string = project.outputs.foundryProjectResourceId

output AZURE_AI_ACCOUNT_NAME string = accountName

output AZURE_AI_PROJECT_NAME string = projectName

@description('Effective Responses API endpoint used by the hosted agent.')
output azureOpenAIResponsesEndpoint string = deployModel
  ? project.outputs.deployedModelResponsesEndpoint
  : existingModelResponsesEndpoint

@description('Whether this sample deployed and owns the model deployment.')
output deployedModelBySample bool = deployModel

@description('Resource ID of the model account when this sample deployed the model.')
output deployedModelAccountId string = deployModel ? project.outputs.foundryAccountResourceId : ''

output meetingDelegateStorageAccountUrl string = project.outputs.meetingDelegateStorageAccountUrl

output meetingDelegateStorageAccountId string = project.outputs.meetingDelegateStorageAccountId

output meetingDelegateStorageContainer string = project.outputs.meetingDelegateStorageContainerName

// These sample-specific names have no microsoft.foundry canonical output key.
// Lower camel case avoids ARM SDK mangling of all-caps output names.
output agentName string = agentName
