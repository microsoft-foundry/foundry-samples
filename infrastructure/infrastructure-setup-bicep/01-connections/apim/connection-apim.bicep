/*
Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This comprehensive template demonstrates how to add an APIM connection
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

// ========================================
// REQUIRED PARAMETERS
// ========================================

@description('Resource ID of the AI Foundry project')
param projectResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.CognitiveServices/accounts/sample-foundry-account/projects/sample-project'

@description('Resource ID of the APIM service')
param apimResourceId string = '/subscriptions/12345678-1234-1234-1234-123456789abc/resourceGroups/rg-sample/providers/Microsoft.ApiManagement/service/sample-apim'

@description('Name of the API in APIM')
param apiName string = 'sample-api'

// ========================================
// BASIC CONFIGURATION
// ========================================

@description('Name for the connection (auto-generated if empty)')
param connectionName string = ''

@description('APIM subscription name for API key auth')
param apimSubscriptionName string = 'master'

@allowed(['ApiKey'])
@description('Authentication type')
param authType string = 'ApiKey'

@description('Share connection to all project users')
param isSharedToAll bool = false

// 1. REQUIRED - Basic APIM Configuration
@allowed(['true', 'false'])
@description('Whether deployment name is in URL path vs query parameter')
param deploymentInPath string = 'true'

@description('API version for inference calls (chat completions, embeddings)')
param inferenceAPIVersion string = ''

// 2. OPTIONAL - Deployment API Version
@description('API version for deployment management (optional)')
param deploymentAPIVersion string = ''

// 3. OPTIONAL - Dynamic Discovery Configuration
@description('Endpoint for listing models (enables dynamic discovery)')
param listModelsEndpoint string = ''

@description('Endpoint for getting model details (enables dynamic discovery)')
param getModelEndpoint string = ''

@description('Provider for model discovery (AzureOpenAI, etc.)')
param deploymentProvider string = ''

// 4. OPTIONAL - Static Model List
@description('Static model list (array of model objects, optional)')
param staticModels array = []

// 5. OPTIONAL - Custom Headers
@description('Custom headers (object with string key-value pairs, optional)')
param customHeaders object = {}

// 6. OPTIONAL - Custom Authentication Configuration
@description('Authentication configuration (object for custom auth headers)')
param authConfig object = {}

// Generate connection name if not provided
var apimServiceName = split(apimResourceId, '/')[8]
var generatedConnectionName = 'apim-${apimServiceName}-${apiName}'
var finalConnectionName = connectionName != '' ? connectionName : generatedConnectionName

// ========================================
// Conditional Metadata Construction Logic
// All complex objects (arrays, objects) must be serialized using string() function
// ========================================

// Helper variables for conditional logic
var hasDeploymentAPIVersion = deploymentAPIVersion != ''
var hasInferenceAPIVersion = inferenceAPIVersion != ''
var hasModelDiscovery = listModelsEndpoint != '' && getModelEndpoint != '' && deploymentProvider != ''
var hasStaticModels = length(staticModels) > 0
var hasCustomHeaders = !empty(customHeaders)
var hasAuthConfig = !empty(authConfig)

// Validation: Fail deployment if both static models and dynamic discovery are configured
var bothConfiguredError = hasModelDiscovery && hasStaticModels
var validationMessage = bothConfiguredError ? 'ERROR: Cannot configure both static models and dynamic discovery. Use either staticModels array OR modelDiscovery parameters, not both.' : ''

// Validation: Fail deployment if neither static models nor dynamic discovery is configured
var neitherConfiguredError = !hasModelDiscovery && !hasStaticModels
var neitherConfiguredMessage = 'ERROR: Must configure either static models (staticModels array) OR dynamic discovery (listModelsEndpoint, getModelEndpoint, deploymentProvider). Cannot have neither.'

// Force deployment failure if both are configured
resource deploymentValidation 'Microsoft.Resources/deploymentScripts@2023-08-01' = if (bothConfiguredError) {
  name: 'validation-error-${uniqueString(resourceGroup().id)}'
  location: resourceGroup().location
  kind: 'AzurePowerShell'
  properties: {
    azPowerShellVersion: '8.0'
    scriptContent: 'throw "${validationMessage}"'
    retentionInterval: 'PT1H'
  }
}

// Force deployment failure if neither are configured
resource configValidation 'Microsoft.Resources/deploymentScripts@2023-08-01' = if (neitherConfiguredError) {
  name: 'config-validation-error-${uniqueString(resourceGroup().id)}'
  location: resourceGroup().location
  kind: 'AzurePowerShell'
  properties: {
    azPowerShellVersion: '8.0'
    scriptContent: 'throw "${neitherConfiguredMessage}"'
    retentionInterval: 'PT1H'
  }
}

// Build metadata using conditional union - includes only non-empty parameters
var metadata = union(
  // Always include basic configuration
  {
    deploymentInPath: deploymentInPath
  },
  // Conditionally include inference API version
  hasInferenceAPIVersion ? {
    inferenceAPIVersion: inferenceAPIVersion
  } : {},
  // Conditionally include deployment API version
  hasDeploymentAPIVersion ? {
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
  } : {},
  // Conditionally include custom auth configuration
  hasAuthConfig ? {
    authConfig: string(authConfig)
  } : {}
)

// ========================================
// DEPLOYMENT
// ========================================

module apimConnection 'modules/apim-connection-common.bicep' = if (!bothConfiguredError && !neitherConfiguredError) {
  name: 'unified-apim-connection'
  params: {
    projectResourceId: projectResourceId
    connectionName: finalConnectionName
    apimResourceId: apimResourceId
    apiName: apiName
    apimSubscriptionName: apimSubscriptionName
    authType: authType
    isSharedToAll: isSharedToAll
    metadata: metadata
  }
}

// ========================================
// OUTPUTS
// ========================================

@description('Name of the created connection')
output connectionName string = finalConnectionName

@description('Final metadata configuration')
output metadata object = metadata

@description('Authentication type used')
output authType string = authType

// Outputs for verification
output hasStaticModels bool = hasStaticModels
output hasModelDiscovery bool = hasModelDiscovery
output hasCustomHeaders bool = hasCustomHeaders
