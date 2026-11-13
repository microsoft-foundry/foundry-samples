targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate a short unique hash for resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Enable private networking (private endpoints, restricted public access). Default keeps the deployment simple.')
param enableNetworkIsolation bool = false

@description('Enable storage lifecycle management (auto-tier and expire old blobs).')
param enableStorageLifecycle bool = false

@description('Principal ID of the user/service running the deployment, granted data-plane access for testing. Leave empty to skip.')
param deployerPrincipalId string = ''

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  solution: 'ingestion-client-v2'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    environmentName: environmentName
    tags: tags
    enableNetworkIsolation: enableNetworkIsolation
    enableStorageLifecycle: enableStorageLifecycle
    deployerPrincipalId: deployerPrincipalId
  }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output SERVICE_FUNCTIONS_NAME string = resources.outputs.functionAppName
output INPUT_STORAGE_ACCOUNT string = resources.outputs.inputStorageAccountName
output OUTPUT_STORAGE_ACCOUNT string = resources.outputs.outputStorageAccountName
output INPUT_AUDIO_CONTAINER string = resources.outputs.audioInputContainer
output CONFIG_CONTAINER string = resources.outputs.configContainer
output FOUNDRY_ENDPOINT string = resources.outputs.foundryEndpoint
