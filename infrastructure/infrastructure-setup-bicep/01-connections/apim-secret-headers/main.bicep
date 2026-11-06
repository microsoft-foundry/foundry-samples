targetScope = 'resourceGroup'

@description('Existing Foundry account in THIS deployment resource group.')
param accountName string

@description('Existing project under accountName. The project must have a managed identity.')
param projectName string

@description('Existing APIM model API base URL, without a trailing slash. Use the actual endpoint for your cloud.')
param targetUrl string

@description('Entra token audience accepted by the gateway, for example its api:// application ID URI. This is separate from the subscription key.')
param audience string

@description('Existing deployment name exposed by the gateway.')
param modelDeploymentName string

@description('Underlying model name, which may differ from the deployment name.')
param modelName string

@description('Underlying model version exposed by the gateway.')
param modelVersion string

@description('Model connection name. Agents reference <connectionName>/<modelDeploymentName>.')
param connectionName string = 'apim-private-header'

@description('Header whose value is stored as a secret in the companion connection.')
param headerName string = 'Ocp-Apim-Subscription-Key'

@secure()
@minLength(1)
@description('Gateway subscription key. Supply securely, preferably through an ARM Key Vault parameter reference. Never place the value in metadata or outputs.')
param subscriptionKey string

@description('Inference API version forwarded through the gateway.')
param inferenceAPIVersion string = '2025-04-01-preview'

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

var companionName = 'secret-headers-${uniqueString(project.id, connectionName)}'

resource secretHeaderConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-07-01' = {
  parent: project
  name: companionName
  properties: {
    category: 'CustomKeys'
    authType: 'CustomKeys'
    target: targetUrl
    isSharedToAll: false
    credentials: {
      keys: {
        header0: subscriptionKey
      }
    }
    metadata: {
      secretHeadersFor: connectionName
    }
  }
}

resource modelConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-07-01' = {
  parent: project
  name: connectionName
  properties: {
    category: 'ApiManagement'
    authType: 'ProjectManagedIdentity'
    audience: audience
    target: targetUrl
    isSharedToAll: false
    credentials: {}
    metadata: {
      deploymentInPath: 'true'
      inferenceAPIVersion: inferenceAPIVersion
      customHeaders: '{}'
      models: string([
        {
          name: modelDeploymentName
          properties: {
            model: {
              name: modelName
              version: modelVersion
              format: 'OpenAI'
            }
          }
        }
      ])
      secretHeaders: string({
        '${headerName}': {
          connection: secretHeaderConnection.name
          key: 'header0'
        }
      })
    }
  }
}

output connectionId string = modelConnection.id
output connectionName string = modelConnection.name
output secretHeaderConnectionId string = secretHeaderConnection.id
output modelReference string = '${connectionName}/${modelDeploymentName}'
