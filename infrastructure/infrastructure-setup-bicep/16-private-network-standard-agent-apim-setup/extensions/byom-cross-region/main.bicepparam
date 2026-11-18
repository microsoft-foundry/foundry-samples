using './main.bicep'

// ---------------------------------------------------------------------------
// Project region (Foundry account, project, VNet, APIM all land here)
// ---------------------------------------------------------------------------
param location = 'canadaeast'
param aiServices = 'aiservices'
param firstProjectName = 'project'
param projectDescription = 'Cross-region private BYOM via APIM'
param displayName = 'cross-region BYOM project'

// Project-region model (covers local fallbacks; backend hosts the heavyweight ones)
param projectModelName = 'gpt-4o'
param projectModelFormat = 'OpenAI'
param projectModelVersion = '2024-11-20'
param projectModelSkuName = 'GlobalStandard'
param projectModelCapacity = 30

// Optional temporary SDK caller access. Leave empty for private-only access.
// param developerIpCidr = '203.0.113.10/32'

// ---------------------------------------------------------------------------
// VNet
// ---------------------------------------------------------------------------
param vnetName = 'agent-vnet-test'
param vnetAddressPrefix = '192.168.0.0/16'
param agentSubnetName = 'agent-subnet'
param peSubnetName = 'pe-subnet'
param backendPeSubnetName = 'backend-pe'
param backendPeSubnetPrefix = '192.168.3.0/27'
param apimOutboundSubnetName = 'apim-outbound'
param apimOutboundSubnetPrefix = '192.168.2.0/27'

// ---------------------------------------------------------------------------
// APIM (create new — leave apiManagementResourceId empty)
// ---------------------------------------------------------------------------
param apimName = 'apim-aigw-byom'
param publisherEmail = 'platform-eng@contoso.com'
param publisherName = 'Contoso Platform Engineering'
param apiManagementResourceId = ''

// ---------------------------------------------------------------------------
// Backend Foundry account (different region — where the gpt-5* models live)
// ---------------------------------------------------------------------------
param backendLocation = 'japaneast'
param backendAccountName = 'aiservices-backend-jpe'
param backendModelDeployments = [
  {
    name: 'gpt-4o'
    format: 'OpenAI'
    version: '2024-11-20'
    skuName: 'GlobalStandard'
    capacity: 10
  }
  {
    name: 'gpt-5'
    format: 'OpenAI'
    version: '2025-08-07'
    skuName: 'GlobalStandard'
    capacity: 10
  }
  {
    name: 'gpt-5.1'
    format: 'OpenAI'
    version: '2025-11-13'
    skuName: 'GlobalStandard'
    capacity: 10
  }
]

// ---------------------------------------------------------------------------
// BYOM connection
// ---------------------------------------------------------------------------
param connectionName = 'ai-gateway'
// Optional deterministic APIM mock model for connectivity testing. Empty disables it.
param mockModelName = ''
param inferenceApiVersion = '2024-10-21'

// Scenario 2: direct connection to the backend Foundry account. Enabling this
// intentionally enables that account's public endpoint and key authentication.
param enableDirectFoundryConnection = false
param directFoundryConnectionName = 'foundry-direct'

// Scenario 3: third-party OpenAI-compatible provider. Keep disabled until the
// target URL, model metadata, and secure thirdPartyApiKey parameter are supplied.
param enableThirdPartyConnection = false
param thirdPartyConnectionName = 'third-party-models'
param thirdPartyTargetUrl = ''
param thirdPartyModels = []

// Application (client) ID of the Foundry project's system-assigned managed
// identity. For the first deployment use this placeholder, resolve the created
// identity principal to its appId, then redeploy with the same timestamp and
// resource names. See the README two-pass bootstrap instructions.
param projectMiClientId = '00000000-0000-0000-0000-000000000000'

// ---------------------------------------------------------------------------
// BYO dependencies (leave empty to create new ones)
// ---------------------------------------------------------------------------
param aiSearchResourceId = ''
param azureStorageAccountResourceId = ''
param azureCosmosDBAccountResourceId = ''
