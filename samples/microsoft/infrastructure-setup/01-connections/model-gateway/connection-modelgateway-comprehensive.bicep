/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This comprehensive template demonstrates how to add a ModelGateway connection
with support for ALL ModelGateway metadata parameters. It includes only non-empty parameters in the final configuration.

This template can handle all ModelGateway connection scenarios from the documentation:
1. Basic ModelGateway with defaults (deploymentInPath + inferenceAPIVersion only)
2. ModelGateway with Deployment API Version (adds deploymentAPIVersion)
3. ModelGateway with Dynamic Discovery (adds modelDiscovery configuration)
4. ModelGateway with Static Model List (adds models array)
5. ModelGateway with Custom Headers (adds customHeaders)
6. Any combination of the above

The template uses conditional logic to include only non-empty parameters,
making it flexible for any ModelGateway scenario while avoiding empty metadata.

IMPORTANT: Make sure you are logged into the subscription where the AI Foundry resource exists before deploying.
The connection will be created in the AI Foundry project, so you need to be in that subscription context.
Use: az account set --subscription <foundry-subscription-id>
*/

param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'
param targetUrl string = 'https://your-model-gateway.example.com'
param gatewayName string = 'example-gateway'

// Connection naming - can be overridden via parameter
param connectionName string = ''  // Optional: specify custom connection name

// Connection configuration (ModelGateway only supports ApiKey)
param authType string = 'ApiKey'
param isSharedToAll bool = false

// API key for the ModelGateway endpoint
@secure()
param apiKey string

// 1. REQUIRED - Basic ModelGateway Configuration
param deploymentInPath string = 'false'  // Required: Controls how deployment names are passed
param inferenceAPIVersion string = ''    // Required: API version for model inference calls

// 2. OPTIONAL - Deployment API Version
param deploymentAPIVersion string = ''   // Optional: API version for deployment management

// 3. OPTIONAL - Dynamic Discovery Configuration  
param listModelsEndpoint string = ''     // Optional: Endpoint for listing available models
param getModelEndpoint string = ''       // Optional: Endpoint for getting model details
param deploymentProvider string = ''     // Optional: Provider type (e.g., OpenAI)

// 4. OPTIONAL - Static Model List
param staticModels array = []            // Optional: Predefined list of available models

// 5. OPTIONAL - Custom Headers
param customHeaders object = {}          // Optional: Custom HTTP headers as key-value pairs

// Generate connection name if not provided
var generatedConnectionName = 'modelgateway-${gatewayName}-comprehensive'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// ========================================
// Conditional Metadata Construction Logic
// All complex objects (arrays, objects) must be serialized using string() function
// ========================================

// Helper variables for conditional logic
var hasModelDiscovery = listModelsEndpoint != '' && getModelEndpoint != '' && deploymentProvider != ''
var hasStaticModels = length(staticModels) > 0
var hasCustomHeaders = !empty(customHeaders)

// Validation: Fail deployment if both static models and dynamic discovery are configured
var bothConfiguredError = hasModelDiscovery && hasStaticModels
var validationMessage = bothConfiguredError ? 'ERROR: Cannot configure both static models and dynamic discovery. Use either staticModels array OR modelDiscovery parameters, not both.' : ''

// Force deployment failure if both are configured
resource deploymentValidation 'Microsoft.Resources/deploymentScripts@2023-08-01' = if (bothConfiguredError) {
  name: 'validation-error'
  location: 'westus2'
  kind: 'AzurePowerShell'
  properties: {
    retentionInterval: 'PT1H'
    azPowerShellVersion: '8.0'
    scriptContent: 'throw "${validationMessage}"'
  }
}

// Build metadata using conditional union - includes only non-empty parameters
var metadata = union(
  // Always include basic configuration
  {
    deploymentInPath: deploymentInPath
    inferenceAPIVersion: inferenceAPIVersion
  },
  // Conditionally include deployment API version
  deploymentAPIVersion != '' ? {
    deploymentAPIVersion: deploymentAPIVersion
  } : {},
  // Conditionally include model discovery configuration
  hasModelDiscovery ? { 
    modelDiscovery: string({
      listModelsEndpoint: listModelsEndpoint
      getModelEndpoint: getModelEndpoint
      deploymentProvider: deploymentProvider
    })
  } : {},
  // Conditionally include static models (only if no dynamic discovery)
  hasStaticModels && !hasModelDiscovery ? { 
    models: string(staticModels)
  } : {},
  // Conditionally include custom headers
  hasCustomHeaders ? {
    customHeaders: string(customHeaders)
  } : {}
)

// Deploy the ModelGateway connection using the common module
module modelGatewayConnection 'modules/modelgateway-connection-common.bicep' = {
  name: 'modelgateway-connection-deployment'
  params: {
    projectResourceId: projectResourceId
    targetUrl: targetUrl
    connectionName: finalConnectionName
    authType: authType
    isSharedToAll: isSharedToAll
    apiKey: apiKey
    metadata: metadata
  }
}

// Outputs for verification
output connectionName string = finalConnectionName
output targetUrl string = targetUrl
output metadata object = metadata
output hasStaticModels bool = hasStaticModels
output hasModelDiscovery bool = hasModelDiscovery
output hasCustomHeaders bool = hasCustomHeaders
