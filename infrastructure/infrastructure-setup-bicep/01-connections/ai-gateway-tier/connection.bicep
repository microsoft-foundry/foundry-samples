/*
  ================================================================================
  connection.bicep  — attach a spoke project to the AI Gateway tier hub
  --------------------------------------------------------------------------------
  Creates the "Admin-connected models" connection (ModelGateway + ApiKey) on an
  EXISTING Foundry project, pointing at the hub gateway that main.bicep deployed.
  Run this once per consumer (spoke) project — in the same subscription as the hub
  or a different one. The agent then references the model as
  <connectionName>/<modelName> via the Responses API (golden path step 6).

  Inputs come straight from the hub deployment's outputs (gatewayModelsBaseUrl,
  modelName/modelVersion/modelFormat) plus the gateway runtime key. Retrieve the key
  once from the hub (it is intentionally NOT emitted as a deployment output):

    az rest --method post \
      --url "https://management.azure.com<hub-gateway-resource-id>/apiKeys/default/listSecrets?api-version=2026-09-01-preview" \
      --query primaryKey -o tsv

  Verified against the same connection shape as the all-in-one AI Gateway tier
  samples and 01-connections/model-gateway.
  ================================================================================
*/

targetScope = 'resourceGroup'

@description('Resource ID of the EXISTING spoke project to attach (from golden-path steps 1-2). The account and project must live in THIS resource group.')
param projectResourceId string

@description('Hub gateway OpenAI base URL — the hub deployment output gatewayModelsBaseUrl (e.g. https://<gateway-hostname>/default/models/openai/v1).')
param gatewayModelsBaseUrl string

@description('Runtime key for the hub gateway. Retrieve it from the hub gateway (listSecrets on its apiKeys/default) and pass it here; works cross-subscription.')
@secure()
param gatewayRuntimeKey string

@description('Connection name. Callers reference the model as <connectionName>/<modelName>.')
param connectionName string = 'ai-gateway'

@description('Model name as registered on the gateway — the hub deployment output modelName.')
param modelName string = 'gpt-5.4'

@description('Model version — the hub deployment output modelVersion.')
param modelVersion string = '2026-03-05'

@description('Model format — the hub deployment output modelFormat.')
param modelFormat string = 'OpenAI'

@description('HTTP header the connection uses to send the gateway key. The AI Gateway tier authenticates the api-key header.')
param authHeaderName string = 'api-key'

@description('If true, the connection is visible to every project on the account and appears in the Foundry portal "Admin-connected models" picker.')
param isSharedToAll bool = true

// Parse the existing account + project from the resource ID
// (.../accounts/<account>/projects/<project>).
var aiFoundryName = split(projectResourceId, '/')[8]
var projectName = split(projectResourceId, '/')[10]

// Static model list: lets the runtime resolve "<connectionName>/<modelName>" without
// an extra service lookup, and lets the portal render the model.
var staticModels = [
  {
    name: modelName
    properties: {
      model: {
        name: modelName
        version: modelVersion
        format: modelFormat
      }
    }
  }
]

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

// "Admin-connected models" connection to the AI Gateway tier hub. category
// ModelGateway + ApiKey + isSharedToAll surfaces it in the portal picker;
// deploymentInPath 'false' => the model name goes in the request body, matching the
// gateway's /openai/v1 endpoint; the tier authenticates the api-key header.
resource gatewayConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: connectionName
  properties: {
    category: 'ModelGateway'
    target: gatewayModelsBaseUrl
    authType: 'ApiKey'
    isSharedToAll: isSharedToAll
    credentials: {
      key: gatewayRuntimeKey
    }
    metadata: {
      models: string(staticModels)
      deploymentInPath: 'false'
      authHeaderName: authHeaderName
      authHeaderFormat: '{api_key}'
      customHeaders: '{}'
    }
  }
}

output connectionName string = gatewayConnection.name
output modelReference string = '${connectionName}/${modelName}'
output projectEndpoint string = 'https://${aiFoundryName}.services.ai.azure.com/api/projects/${projectName}'
