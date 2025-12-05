/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add a ModelGateway connection with dynamic model discovery.
ModelGateway connections provide a unified interface for various AI model providers.
Uses ApiKey authentication with dynamic model discovery using API endpoints.

Configuration includes:
- deploymentInPath: Controls how deployment names are passed to the gateway in inference api calls
- inferenceAPIVersion: API version for model inference calls
- deploymentAPIVersion: API version for deployment management calls
- modelDiscovery: Dynamic endpoints for model discovery with OpenAI format

Dynamic model discovery endpoints:
- List Models: /v1/models
- Get Model: /v1/models/{deploymentName}
- Provider: OpenAI format responses

IMPORTANT: Make sure you are logged into the subscription where the AI Foundry resource exists before deploying.
The connection will be created in the AI Foundry project, so you need to be in that subscription context.
Use: az account set --subscription <foundry-subscription-id>
*/

param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'
param targetUrl string = 'https://your-model-gateway.example.com'
param gatewayName string = 'example-gateway'

// Connection configuration (ModelGateway only supports ApiKey)
param authType string = 'ApiKey'
param isSharedToAll bool = false

// Connection naming - can be overridden via parameter
param connectionName string = ''  // Optional: specify custom connection name

// API key for the ModelGateway endpoint
@secure()
param apiKey string

// Generate connection name if not provided
var generatedConnectionName = 'modelgateway-${gatewayName}-dynamic'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// ModelGateway-specific configuration parameters
@allowed([
  'true'
  'false'
])
param deploymentInPath string = 'false'  // Controls how deployment names are passed to the gateway

param inferenceAPIVersion string = ''  // API version for inference calls
param deploymentAPIVersion string = ''  // API version for deployment management calls

// Model discovery configuration (dynamic endpoints)
param listModelsEndpoint string = '/v1/models'  // Endpoint for listing models
param getModelEndpoint string = '/v1/models/{deploymentName}'  // Endpoint for getting specific model
param deploymentProvider string = 'OpenAI'  // Provider format for response parsing

// Build the modelDiscovery object and serialize it as JSON string
var modelDiscoveryObject = {
  listModelsEndpoint: listModelsEndpoint
  getModelEndpoint: getModelEndpoint
  deploymentProvider: deploymentProvider
}

// Build the metadata object for ModelGateway Dynamic Discovery
// All values must be strings, including serialized JSON objects
var modelGatewayMetadata = {
  deploymentInPath: deploymentInPath
  inferenceAPIVersion: inferenceAPIVersion
  deploymentAPIVersion: deploymentAPIVersion
  modelDiscovery: string(modelDiscoveryObject)  // Serialize as JSON string
}

// Use the common module to create the ModelGateway connection
module modelGatewayConnection 'modules/modelgateway-connection-common.bicep' = {
  name: 'modelgateway-connection-dynamic'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    targetUrl: targetUrl
    authType: authType
    isSharedToAll: isSharedToAll
    apiKey: apiKey
    metadata: modelGatewayMetadata
  }
}

// Output information from the connection
output connectionName string = modelGatewayConnection.outputs.connectionName
output connectionId string = modelGatewayConnection.outputs.connectionId
output targetUrl string = modelGatewayConnection.outputs.targetUrl
output authType string = modelGatewayConnection.outputs.authType
output metadata object = modelGatewayConnection.outputs.metadata
