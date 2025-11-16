/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This example demonstrates how to add an Azure API Management connection for a specific API.
This implements Example 2 from the APIM Connection documentation: "APIM with Deployment API Version"
Uses ApiKey authentication with both inference and deployment API versions specified.

Configuration includes:
- deploymentInPath: Controls how deployment names are passed to APIM gateway
- inferenceAPIVersion: API version for model inference calls (chat completions, embeddings, etc.)
- deploymentAPIVersion: API version for deployment management calls (model discovery)

This uses APIM default endpoints:
- List Deployments: /deployments
- Get Deployment: /deployments/{deploymentName}
- Provider: AzureOpenAI

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
var generatedConnectionName = 'apim-${apimServiceName}-${apiName}-v2'
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
param deploymentInPath string = 'true'  // Controls how deployment names are passed to APIM gateway

param inferenceAPIVersion string = '2024-02-01'  // API version for inference calls (chat completions, embeddings, etc.)
param deploymentAPIVersion string = '2025-01-01'  // API version for deployment management calls

// Build the metadata object for Example 2: APIM with Deployment API Version
var example2Metadata = {
  deploymentInPath: deploymentInPath
  inferenceAPIVersion: inferenceAPIVersion
  deploymentAPIVersion: deploymentAPIVersion
}

// Use the common module to create the APIM connection
module apimConnection 'modules/apim-connection-common.bicep' = {
  name: 'apim-connection-example2'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    apimResourceId: apimResourceId
    apiName: apiName
    apimSubscriptionName: apimSubscriptionName
    authType: authType
    isSharedToAll: isSharedToAll
    metadata: example2Metadata
  }
}

// Output information from the connection
output connectionName string = apimConnection.outputs.connectionName
output connectionId string = apimConnection.outputs.connectionId
output targetUrl string = apimConnection.outputs.targetUrl
output authType string = apimConnection.outputs.authType
output metadata object = apimConnection.outputs.metadata
