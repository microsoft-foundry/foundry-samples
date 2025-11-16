/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add a ModelGateway connection with static model discovery.
ModelGateway connections provide a unified interface for various AI model providers.
Uses ApiKey authentication with predefined static list of models.

Configuration includes:
- deploymentInPath: Controls how deployment names are passed to the gateway
- inferenceAPIVersion: API version for model inference calls (chat completions, embeddings, etc.)
- models: Static predefined list of available models

Static model configuration:
- No dynamic discovery endpoints needed
- Predefined model list with deployment names and model details
- Useful when dynamic discovery is not available or desired

IMPORTANT: Make sure you are logged into the subscription where the AI Foundry resource exists before deploying.
The connection will be created in the AI Foundry project, so you need to be in that subscription context.
Use: az account set --subscription <foundry-subscription-id>
*/

param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'
param targetUrl string = 'https://your-model-gateway.example.com/v1'
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
var generatedConnectionName = 'modelgateway-${gatewayName}-static'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// ModelGateway-specific configuration parameters
@allowed([
  'true'
  'false'
])
param deploymentInPath string = 'false'  // Controls how deployment names are passed to the gateway

param inferenceAPIVersion string = '2024-02-01'  // API version for inference calls

// Static model list configuration - accept as parameter
param staticModels array = [
  {
    name: 'gpt-4'
    properties: {
      model: {
        name: 'gpt-4'
        version: '0613'
        format: 'OpenAI'
      }
    }
  }
  {
    name: 'gpt-3.5-turbo'
    properties: {
      model: {
        name: 'gpt-3.5-turbo'
        version: '0613'
        format: 'OpenAI'
      }
    }
  }
  {
    name: 'text-embedding-ada-002'
    properties: {
      model: {
        name: 'text-embedding-ada-002'
        version: '2'
        format: 'OpenAI'
      }
    }
  }
]

// Build the metadata object for ModelGateway Static Models
// All values must be strings, including serialized JSON objects
var modelGatewayMetadata = {
  deploymentInPath: deploymentInPath
  inferenceAPIVersion: inferenceAPIVersion
  models: string(staticModels)  // Serialize static models array as JSON string
}

// Use the common module to create the ModelGateway connection
module modelGatewayConnection 'modules/modelgateway-connection-common.bicep' = {
  name: 'modelgateway-connection-static'
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
