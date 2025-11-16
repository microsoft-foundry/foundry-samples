/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure API Management connection for a specific API.
This implements Example 5 from the APIM Connection documentation: "APIM with Static Model List"
Uses ApiKey authentication with predefined static list of models when deployment APIs are not available.

Configuration includes:
- deploymentInPath: Controls how deployment names are passed to APIM gateway
- inferenceAPIVersion: API version for model inference calls (chat completions, embeddings, etc.)
- models: Static predefined list of available models (when deployment discovery APIs are not available)

Static model configuration:
- No dynamic discovery endpoints needed
- Predefined model list with deployment names and model details
- Useful when APIM doesn't expose deployment discovery APIs

IMPORTANT: Make sure you are logged into the subscription where the AI Foundry resource exists before deploying.
The connection will be created in the AI Foundry project, so you need to be in that subscription context.
Use: az account set --subscription <foundry-subscription-id>
*/

param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'
param apimResourceId string = '/subscriptions/87654321-4321-4321-4321-cba987654321/resourceGroups/rg-sample-apim/providers/Microsoft.ApiManagement/service/sample-apim-service'
param apiName string = 'foundry'
param apimSubscriptionName string = 'master'  // Default subscription name in APIM, update it to your subscription name for apikey auth

// Connection naming - can be overridden via parameter
param connectionName string = ''  // Optional: specify custom connection name

// Generate connection name if not provided
var apimServiceName = split(apimResourceId, '/')[8]
var generatedConnectionName = 'apim-${apimServiceName}-${apiName}-v5'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// Connection configuration
@allowed([
  'ApiKey'
  'AAD'
])
param authType string = 'ApiKey'  // Authentication type for the connection

param isSharedToAll bool = false  // Whether the connection should be shared to all users in the project

// APIM-specific configuration parameters
@allowed([
  'true'
  'false'
])
param deploymentInPath string = 'false'  // Controls how deployment names are passed to APIM gateway

param inferenceAPIVersion string = '2024-02-01'  // API version for inference calls (chat completions, embeddings, etc.)

// Static model list configuration (when deployment APIs are not available)
// Accept static models as parameter - array of model objects
param staticModels array = [
  {
    name: 'gpt-4-deployment'
    properties: {
      model: {
        name: 'gpt-4'
        version: '0613'
        format: 'OpenAI'
      }
    }
  }
  {
    name: 'gpt-35-turbo-deployment' 
    properties: {
      model: {
        name: 'gpt-35-turbo'
        version: '0613'
        format: 'OpenAI'
      }
    }
  }
]

// Build the metadata object for Example 5: APIM with Static Model List
// All values must be strings, including serialized JSON objects
var example5Metadata = {
  deploymentInPath: deploymentInPath
  inferenceAPIVersion: inferenceAPIVersion
  models: string(staticModels)  // Serialize static models array as JSON string
}

// Use the common module to create the APIM connection
module apimConnection 'modules/apim-connection-common.bicep' = {
  name: 'apim-connection-example5'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    apimResourceId: apimResourceId
    apiName: apiName
    apimSubscriptionName: apimSubscriptionName
    authType: authType
    isSharedToAll: isSharedToAll
    metadata: example5Metadata
  }
}

// Output information from the connection
output connectionName string = apimConnection.outputs.connectionName
output connectionId string = apimConnection.outputs.connectionId
output targetUrl string = apimConnection.outputs.targetUrl
output authType string = apimConnection.outputs.authType
output metadata object = apimConnection.outputs.metadata
