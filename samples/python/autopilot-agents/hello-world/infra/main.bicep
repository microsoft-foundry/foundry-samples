targetScope = 'subscription'

@minLength(1)
@description('Name of the azd environment.')
param environmentName string

@minLength(1)
@description('Azure region for new resources. Reused resources retain their existing region.')
param location string

@minLength(1)
@maxLength(90)
@description('Name of the resource group to create or reuse.')
param resourceGroupName string

@description('Whether the resource group already exists and must not be modified.')
param resourceGroupExists bool

@minLength(2)
@maxLength(64)
@description('Name of the Microsoft Foundry resource to create or reuse.')
param foundryResourceName string

@description('Whether the Foundry resource already exists and must not be modified.')
param foundryResourceExists bool

@minLength(2)
@maxLength(64)
@description('Name of the Microsoft Foundry project to create or reuse.')
param foundryProjectName string

@description('Whether the Foundry project already exists and must not be modified.')
param foundryProjectExists bool

@minLength(1)
@description('Name of the model deployment used by the agent.')
param modelDeploymentName string

@description('Whether the model deployment already exists and must not be modified.')
param modelDeploymentExists bool

@description('Model catalog name. Used only when creating a deployment.')
param modelName string

@description('Model provider format. Used only when creating a deployment.')
param modelFormat string

@description('Model version. Used only when creating a deployment.')
param modelVersion string

@description('Model deployment SKU. The provisioning hook defaults new deployments to GlobalStandard.')
param modelSkuName string

// Reused deployments can report zero capacity; new-deployment validation belongs in the hook.
@description('Model deployment capacity. The provisioning hook defaults new deployments to 1.')
param modelCapacity int

resource resourceGroupDeployment 'Microsoft.Resources/resourceGroups@2024-11-01' = if (!resourceGroupExists) {
  name: resourceGroupName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

resource foundryAccountReference 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  scope: az.resourceGroup(resourceGroupName)
  name: foundryResourceName
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  scope: az.resourceGroup(resourceGroupName)
  params: {
    location: foundryResourceExists ? foundryAccountReference.location : location
    environmentName: environmentName
    foundryResourceName: foundryResourceName
    foundryResourceExists: foundryResourceExists
    foundryProjectName: foundryProjectName
    foundryProjectExists: foundryProjectExists
    modelDeploymentName: modelDeploymentName
    modelDeploymentExists: modelDeploymentExists
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
  }
  dependsOn: [
    resourceGroupDeployment
  ]
}

output AZURE_RESOURCE_GROUP string = resourceGroupName
output AZURE_LOCATION string = foundry.outputs.AZURE_LOCATION
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.AZURE_AI_ACCOUNT_NAME
output AZURE_AI_PROJECT_ID string = foundry.outputs.AZURE_AI_PROJECT_ID
output AZURE_AI_PROJECT_NAME string = foundry.outputs.AZURE_AI_PROJECT_NAME
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.FOUNDRY_PROJECT_ENDPOINT
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = modelDeploymentName
output AZURE_AI_AGENT_NAME string = 'hello-world-autopilot'
