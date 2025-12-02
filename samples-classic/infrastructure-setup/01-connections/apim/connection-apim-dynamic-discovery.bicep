/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure API Management connection for a specific API.
This implements Example 4 from the APIM Connection documentation: "APIM with Dynamic Discovery with OpenAI like deployments API"
Uses ApiKey authentication with dynamic model discovery using custom endpoints.

Configuration includes:
- deploymentInPath: Controls how deployment names are passed to APIM gateway
- modelDiscovery: Custom endpoints for dynamic model discovery with OpenAI format

Dynamic model discovery endpoints:
- List Models: v1/models
- Get Model: v1/models/{deploymentName}
- Provider: OpenAI format responses for deployments API

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
var generatedConnectionName = 'apim-${apimServiceName}-${apiName}-v4'
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

// Model discovery configuration (custom endpoints)
param listModelsEndpoint string = 'v1/models'  // Custom endpoint for listing models
param getModelEndpoint string = 'v1/models/{deploymentName}'  // Custom endpoint for getting specific model
param deploymentProvider string = 'OpenAI'  // Provider format for response parsing

// Build the modelDiscovery object and serialize it as JSON string
var modelDiscoveryObject = {
  listModelsEndpoint: listModelsEndpoint
  getModelEndpoint: getModelEndpoint
  deploymentProvider: deploymentProvider
}

// Build the metadata object for Example 3: APIM with Dynamic Discovery
// All values must be strings, including serialized JSON objects
var example3Metadata = {
  deploymentInPath: deploymentInPath
  modelDiscovery: string(modelDiscoveryObject)  // Serialize as JSON string
}

// Use the common module to create the APIM connection
module apimConnection 'modules/apim-connection-common.bicep' = {
  name: 'apim-connection-example4'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    apimResourceId: apimResourceId
    apiName: apiName
    apimSubscriptionName: apimSubscriptionName
    authType: authType
    isSharedToAll: isSharedToAll
    metadata: example3Metadata
  }
}

// Output information from the connection
output connectionName string = apimConnection.outputs.connectionName
output connectionId string = apimConnection.outputs.connectionId
output targetUrl string = apimConnection.outputs.targetUrl
output authType string = apimConnection.outputs.authType
output metadata object = apimConnection.outputs.metadata
