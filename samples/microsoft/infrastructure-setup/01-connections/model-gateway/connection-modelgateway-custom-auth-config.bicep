/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add a ModelGateway connection with custom authentication configuration.
This shows how to configure the connection to send the API key as an Authorization header with Bearer format.
Uses ApiKey authentication with authConfig to customize authentication headers.

Configuration includes:
- authConfig: Custom authentication configuration to send API key as "Authorization: Bearer {api_key}"
- deploymentInPath: Controls how deployment names are passed to the gateway
- inferenceAPIVersion: API version for model inference calls
- modelDiscovery: Dynamic endpoints for model discovery with OpenAI format

Use case: When the target service expects API key authentication via Authorization Bearer header
instead of the default authentication methods.

IMPORTANT: Make sure you are logged into the subscription where the AI Foundry resource exists before deploying.
The connection will be created in the AI Foundry project, so you need to be in that subscription context.
Use: az account set --subscription <foundry-subscription-id>
*/

param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'
param targetUrl string = 'https://api.openai.com'
param gatewayName string = 'custom-auth-gateway'

// Connection configuration (ModelGateway only supports ApiKey)
param authType string = 'ApiKey'
param isSharedToAll bool = false

// Connection naming - can be overridden via parameter
param connectionName string = ''  // Optional: specify custom connection name

// API key for the ModelGateway endpoint
@secure()
param apiKey string

// Generate connection name if not provided
var generatedConnectionName = 'modelgateway-${gatewayName}-custom-auth'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// ModelGateway-specific configuration parameters
@allowed([
  'true'
  'false'
])
param deploymentInPath string = 'false'  // Controls how deployment names are passed to the gateway

param inferenceAPIVersion string = ''  // API version for inference calls

// Model discovery configuration (dynamic endpoints) 
param listModelsEndpoint string = '/v1/models'  // Endpoint for listing models
param getModelEndpoint string = '/v1/models/{deploymentName}'  // Endpoint for getting specific model
param deploymentProvider string = 'OpenAI'  // Provider format for response parsing

// Custom authentication configuration (Bearer token format) - from documentation
param authConfig object = {
  type: 'api_key'
  name: 'Authorization'
  format: 'Bearer {api_key}'
}

// Build the modelDiscovery object and serialize it as JSON string
var modelDiscoveryObject = {
  listModelsEndpoint: listModelsEndpoint
  getModelEndpoint: getModelEndpoint
  deploymentProvider: deploymentProvider
}

// Build the metadata object for ModelGateway Custom Auth Configuration
// All values must be strings, including serialized JSON objects
var customAuthMetadata = {
  deploymentInPath: deploymentInPath
  inferenceAPIVersion: inferenceAPIVersion
  modelDiscovery: string(modelDiscoveryObject)  // Serialize as JSON string
  authConfig: string(authConfig)  // Serialize as JSON string - from documentation
}

// Use the common module to create the ModelGateway connection
module modelGatewayConnection 'modules/modelgateway-connection-common.bicep' = {
  name: 'modelgateway-connection-custom-auth'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    targetUrl: targetUrl
    authType: authType
    isSharedToAll: isSharedToAll
    apiKey: apiKey
    metadata: customAuthMetadata
  }
}

// Output information from the connection
output connectionName string = modelGatewayConnection.outputs.connectionName
output connectionId string = modelGatewayConnection.outputs.connectionId
output targetUrl string = modelGatewayConnection.outputs.targetUrl
output authType string = modelGatewayConnection.outputs.authType
output metadata object = modelGatewayConnection.outputs.metadata
