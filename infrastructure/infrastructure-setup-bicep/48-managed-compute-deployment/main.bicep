targetScope = 'resourceGroup'

@description('Name of the existing Microsoft Foundry account. The account must use kind AIServices.')
@minLength(2)
@maxLength(64)
param foundryAccountName string

@description('Seed used to derive a stable six-character alphanumeric deployment-name suffix.')
param deploymentNameSeed string

@description('Microsoft Foundry catalog model asset ID.')
param modelId string = 'azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5'

@description('Microsoft Foundry catalog deployment-template asset ID.')
param deploymentTemplateId string = 'azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest'

@description('Managed-compute accelerator family for the selected example template.')
@allowed([
  'A100_80GB'
])
param acceleratorType string = 'A100_80GB'

@description('Number of model instances. The selected example template uses one accelerator per instance.')
@minValue(1)
param capacity int = 1

@description('Deployment-template version upgrade policy.')
@allowed([
  'NoAutoUpgrade'
  'OnceCurrentVersionExpired'
  'OnceNewDefaultVersionAvailable'
])
param versionUpgradeOption string = 'OnceNewDefaultVersionAvailable'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

var deploymentSuffix = take(uniqueString(deploymentNameSeed), 6)
var managedComputeDeploymentName = 'gemma-4-31b-it-a100-${deploymentSuffix}'

resource managedComputeDeployment 'Microsoft.CognitiveServices/accounts/managedComputeDeployments@2026-07-15-preview' = {
  parent: foundryAccount
  name: managedComputeDeploymentName
  sku: {
    name: 'GlobalManagedCompute'
    capacity: capacity
  }
  properties: {
    model: modelId
    deploymentTemplate: deploymentTemplateId
    acceleratorType: acceleratorType
    versionUpgradeOption: versionUpgradeOption
  }
}

output deploymentResourceId string = managedComputeDeployment.id
output deploymentName string = managedComputeDeployment.name
output acceleratorType string = acceleratorType
output capacity int = capacity
