targetScope = 'resourceGroup'

@description('Name of the AI Foundry account (AI Services resource)')
param aiFoundryAccountName string

@description('Name of the AI Foundry project')
param aiFoundryProjectName string

@description('Connection name for the Playwright workspace')
param connectionName string = 'browserautomation'

@description('Authentication type for the connection')
@allowed([
  'ApiKey'
  'ProjectManagedIdentity'
  'AgenticIdentityToken'
])
param authType string = 'ProjectManagedIdentity'

@secure()
@description('API key for the Playwright workspace (required when authType is ApiKey)')
param apiKey string = ''

@description('Existing Playwright workspace ARM resource ID. If empty, a new workspace is created in this resource group.')
param playwrightResourceId string = ''

@description('Region for the new Playwright workspace (only used when creating a new workspace)')
param playwrightRegion string = ''

@description('Name for the new Playwright workspace (only used when creating a new workspace)')
param playwrightWorkspaceName string = 'pww-${uniqueString(resourceGroup().id)}'

// Determine if we need to create a new workspace
var createNewWorkspace = empty(playwrightResourceId)

// Reference the existing AI account and project
resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryAccountName

  resource project 'projects' existing = {
    name: aiFoundryProjectName
  }
}

// ─── Path A: Create new workspace ────────────────────────────────────────────

resource playwrightWorkspace 'Microsoft.LoadTestService/playwrightWorkspaces@2025-09-01' = if (createNewWorkspace) {
  name: playwrightWorkspaceName
  location: playwrightRegion
  properties: {
    regionalAffinity: 'Enabled'
  }
}

resource connectionForNewWorkspace 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (createNewWorkspace) {
  parent: aiAccount::project
  name: connectionName
  properties: {
    category: 'PlaywrightWorkspace'
    target: '${replace(playwrightWorkspace.properties.dataplaneUri, '.api.playwright.microsoft.com', '.mcp.playwright.microsoft.com')}/mcp'
    authType: authType
    audience: 'https://mcp.playwright.microsoft.com'
    isSharedToAll: true
    credentials: null
    metadata: {
      resourceId: playwrightWorkspace.id
    }
  }
}

// ─── Path B: Use existing workspace ─────────────────────────────────────────

module existingPwwLookup 'playwright-lookup.bicep' = if (!createNewWorkspace) {
  name: 'playwright-lookup'
  scope: resourceGroup(split(playwrightResourceId, '/')[2], split(playwrightResourceId, '/')[4])
  params: {
    playwrightWorkspaceName: last(split(playwrightResourceId, '/'))
  }
}

resource connectionForExistingWorkspace 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (!createNewWorkspace) {
  parent: aiAccount::project
  name: connectionName
  properties: {
    category: 'PlaywrightWorkspace'
    target: '${replace(existingPwwLookup.outputs.dataplaneUri, '.api.playwright.microsoft.com', '.mcp.playwright.microsoft.com')}/mcp'
    authType: authType
    audience: 'https://mcp.playwright.microsoft.com'
    isSharedToAll: true
    credentials: authType == 'ApiKey' ? {
      key: apiKey
    } : null
    metadata: {
      resourceId: playwrightResourceId
    }
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────────────

output connectionName string = connectionName
output playwrightResourceId string = createNewWorkspace ? playwrightWorkspace.id : playwrightResourceId
