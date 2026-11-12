/*
  ================================================================================
  main.bicep  — TC01 for the AI Gateway tier (preview), END TO END in Bicep
  --------------------------------------------------------------------------------
  Provisions the whole TC01 happy path in one deployment — no portal steps:

    1-2. Foundry account + project + gpt-5.4 model deployment.
    3.   AI Gateway tier instance (Microsoft.ApiManagement/service, AIGateway SKU)
         with a system-assigned identity, and a Foundry model provider that imports
         the account over MANAGED IDENTITY (keyless — the gateway MI gets the
         Foundry User role on the account).
    4.   The model registered on the gateway with a token-limit policy, plus a
         runtime access key for callers.

  Then test with samples/test-model-via-gateway.py (step 5).

  Release-gated preview: the AIGateway SKU deploys only where it is enabled
  (East US 2, Sweden Central). Pattern from the Azure-Samples repo
  simple-foundry-hosted-agent-python-aigateway.

  Verified against:
    https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools
    https://learn.microsoft.com/azure/api-management/ai-gateway-govern-secure-assets
    https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry
  ================================================================================
*/

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Foundry account / project
// ---------------------------------------------------------------------------
@description('Base name for the Foundry account. A short unique suffix is appended.')
@maxLength(9)
param aiServicesName string = 'foundry'

@description('Name of the project created under the account.')
param projectName string = 'gateway-project'

@description('Project description.')
param projectDescription string = 'AI Gateway tier TC01 sample.'

@description('Project display name.')
param projectDisplayName string = 'AI Gateway tier TC01'

@allowed([
  'eastus2'
  'swedencentral'
])
@description('Region for the account, project, and model. Restricted to the AI Gateway tier preview regions so the model is co-located with the gateway.')
param location string = 'eastus2'

// ---------------------------------------------------------------------------
// Model deployment
// ---------------------------------------------------------------------------
@description('Model to deploy. The AI Gateway tier imports this deployment and callers reference it by this name in the request "model" field.')
param modelName string = 'gpt-5.4'

@description('Model format. Example: OpenAI.')
param modelFormat string = 'OpenAI'

@description('Model version. Ensure this version is available in your region: az cognitiveservices account list-models.')
param modelVersion string = '2026-03-05'

@description('Model deployment SKU name. Example: GlobalStandard.')
param modelSkuName string = 'GlobalStandard'

@description('Model deployment capacity in thousands of TPM. gpt-5.4 may require more than the default; set a value your subscription has quota for (the reference deployment used 681).')
param modelCapacity int = 40

// ---------------------------------------------------------------------------
// AI Gateway tier
// ---------------------------------------------------------------------------
@description('Globally unique AI Gateway name. Resolves to <name>.azure-api.net. Leave empty to auto-generate.')
param gatewayName string = ''

@description('Publisher email required by the API Management service at create time.')
param publisherEmail string = 'noreply@example.com'

@description('Publisher organization name required by the API Management service at create time.')
param publisherName string = 'AI Gateway TC01'

@description('Tokens-per-minute budget enforced on the model by the gateway token-limit policy. Low by default so the --repeat test visibly throttles (HTTP 429).')
param tokensPerMinute int = 100

// ---------------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------------
param deploymentTimestamp string = utcNow('yyyyMMddHHmmss')
var uniqueSuffix = substring(uniqueString('${resourceGroup().id}-${deploymentTimestamp}'), 0, 4)
var accountName = toLower('${aiServicesName}${uniqueSuffix}')

// ===========================================================================
// Foundry account (AIServices) — system-assigned identity, NO user-assigned MI.
// Local auth is DISABLED to enforce keyless (managed-identity) backend access.
// ===========================================================================
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
  }
}

// ===========================================================================
// Model deployment (imported by the gateway, referenced by name at call time)
// ===========================================================================
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: modelName
  sku: {
    capacity: modelCapacity
    name: modelSkuName
  }
  properties: {
    model: {
      name: modelName
      format: modelFormat
      version: modelVersion
    }
  }
}

// ===========================================================================
// Project
// ===========================================================================
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectDisplayName
  }
  dependsOn: [
    modelDeployment
  ]
}

// ===========================================================================
// AI Gateway tier instance — Microsoft.ApiManagement/service with the AIGateway
// SKU. Release-gated preview: deploys only where the SKU is enabled (East US 2,
// Sweden Central).
// ===========================================================================
var effectiveGatewayName = empty(gatewayName) ? 'aigw${uniqueSuffix}' : gatewayName
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var foundryEndpoint = endsWith(account.properties.endpoint, '/') ? account.properties.endpoint : '${account.properties.endpoint}/'

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: effectiveGatewayName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'AIGateway'
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

// Grant the gateway's managed identity Foundry User on the account (keyless backend).
resource foundryUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, aiGateway.id, foundryUserRoleId)
  properties: {
    principalId: aiGateway.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
  }
}

// The AIGateway SKU auto-creates a 'default' workspace that holds providers/models.
resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

// Foundry model provider — imports from the account using managed identity.
resource foundryProvider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: 'foundry'
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry'
    foundry: {
      endpoint: foundryEndpoint
      resourceIds: [
        account.id
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
  dependsOn: [
    foundryUserRole
    modelDeployment
  ]
}

// Register the deployment as a gateway model, with a token-limit policy (TC01 step 4).
resource gatewayModel 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: modelName
  properties: {
    displayName: modelName
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: modelDeployment.id
      modelName: modelDeployment.name
      modelVersion: modelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokensPerMinute
        counterKey: 'Identity'
      }
    ]
  }
}

// A runtime access key that clients send in the api-key header.
resource runtimeKey 'Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: 'default'
  properties: {
    displayName: 'TC01 runtime key'
  }
}

// ===========================================================================
// Outputs
// ===========================================================================
output subscriptionId string = subscription().subscriptionId
output resourceGroupName string = resourceGroup().name
output accountName string = account.name
output accountId string = account.id
output projectName string = project.name
output gatewayName string = aiGateway.name
output gatewayModelsBaseUrl string = '${aiGateway.properties.gatewayUrl}/default/models/openai/v1'
output modelName string = modelName
output gatewayPrincipalId string = aiGateway.identity.principalId
output location string = location
