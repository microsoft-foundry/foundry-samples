/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This comprehensive template demonstrates how to add an Azure API Management connection for a specific API
with support for ALL APIM metadata parameters. It includes only non-empty parameters in the final configuration.

This template can handle all APIM connection scenarios from the documentation:
1. Basic APIM with defaults (deploymentInPath + inferenceAPIVersion only)
2. APIM with Deployment API Version (adds deploymentAPIVersion)
3. APIM with Dynamic Discovery (adds modelDiscovery configuration)
4. APIM with Static Model List (adds models array)
5. APIM with Custom Headers (adds customHeaders)
6. Any combination of the above

The template uses conditional logic to include only non-empty parameters,
making it flexible for any APIM scenario while avoiding empty metadata.

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
var generatedConnectionName = 'apim-${apimServiceName}-${apiName}-comprehensive'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// Connection configuration
@allowed([
  'ApiKey'
  'AAD'
])
param authType string = 'ApiKey'  // Authentication type for the connection

param isSharedToAll bool = false  // Whether the connection should be shared to all users in the project

// ========================================
// APIM METADATA PARAMETERS (ALL OPTIONAL)
// ========================================

// 1. REQUIRED - DeploymentInPath (always needed)
@allowed([
  'true'
  'false'
])
param deploymentInPath string = 'true'  // Controls how deployment names are passed to APIM gateway

// 2. OPTIONAL - InferenceAPIVersion
param inferenceAPIVersion string = ''  // API version for inference calls (chat completions, embeddings, etc.)

// 3. OPTIONAL - DeploymentAPIVersion  
param deploymentAPIVersion string = ''  // API version for deployment management calls

// 4. OPTIONAL - ModelDiscovery (Dynamic Discovery)
param listModelsEndpoint string = ''  // Endpoint to retrieve all available models (e.g., "/v1/models")
param getModelEndpoint string = ''    // Endpoint to get specific model details (e.g., "/v1/models/{deploymentName}")
@allowed([
  ''
  'OpenAI'
  'AzureOpenAI'
])
param deploymentProvider string = ''   // Provider format for response parsing

// 5. OPTIONAL - Static Models (alternative to dynamic discovery)
param staticModels array = []  // Array of predefined models with structure: [{name: string, properties: {model: {name: string, version: string, format: string}}}]

// 6. OPTIONAL - CustomHeaders
param customHeaders object = {}  // Custom headers to be passed to APIM gateway

// ========================================
// METADATA CONSTRUCTION WITH CONDITIONALS
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
    azPowerShellVersion: '8.0'
    scriptContent: 'throw "${validationMessage}"'
    retentionInterval: 'PT1H'
  }
}

// Build metadata object in one go with conditional properties
var finalMetadata = union(
  {
    // Required field
    deploymentInPath: deploymentInPath
  }, 
  // Optional simple fields
  inferenceAPIVersion != '' ? { inferenceAPIVersion: inferenceAPIVersion } : {},
  deploymentAPIVersion != '' ? { deploymentAPIVersion: deploymentAPIVersion } : {},
  // Optional complex objects (mutually exclusive: either dynamic discovery OR static models, not both)
  hasModelDiscovery ? { 
    modelDiscovery: string({
      listModelsEndpoint: listModelsEndpoint
      getModelEndpoint: getModelEndpoint
      deploymentProvider: deploymentProvider
    })
  } : {},
  hasStaticModels && !hasModelDiscovery ? { 
    models: string(staticModels) 
  } : {},
  hasCustomHeaders ? { 
    customHeaders: string(customHeaders) 
  } : {}
)

// ========================================
// CONNECTION DEPLOYMENT
// ========================================

module apimConnection 'modules/apim-connection-common.bicep' = {
  name: 'apim-connection-deployment'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    apimResourceId: apimResourceId
    apiName: apiName
    apimSubscriptionName: apimSubscriptionName
    authType: authType
    isSharedToAll: isSharedToAll
    metadata: finalMetadata
  }
}

// ========================================
// OUTPUTS
// ========================================

output connectionName string = apimConnection.outputs.connectionName
output connectionId string = apimConnection.outputs.connectionId
output targetUrl string = apimConnection.outputs.targetUrl
output authType string = apimConnection.outputs.authType
output metadata object = apimConnection.outputs.metadata

// Debug outputs to verify metadata construction
output finalMetadata object = finalMetadata
output hasModelDiscovery bool = hasModelDiscovery
output hasStaticModels bool = hasStaticModels
output hasCustomHeaders bool = hasCustomHeaders
