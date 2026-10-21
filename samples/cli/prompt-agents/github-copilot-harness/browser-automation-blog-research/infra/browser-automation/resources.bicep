@description('Name of the Microsoft Foundry account.')
param accountName string

@description('Name of the Microsoft Foundry project.')
param projectName string

@description('Name of the azd environment.')
param environmentName string

@description('Location for the Playwright workspace.')
param playwrightLocation string

param tags object = {}

var resourceToken = take(toLower(uniqueString(subscription().id, environmentName, resourceGroup().id)), 8)
var playwrightWorkspaceName = 'pw-${resourceToken}'
var playwrightWorkspaceContributorRoleId = '78cf819f-0969-4ebe-8759-015c6efcd5bf'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: foundryAccount
  name: projectName
}

resource playwrightWorkspace 'Microsoft.LoadTestService/playwrightWorkspaces@2025-09-01' = {
  name: playwrightWorkspaceName
  location: playwrightLocation
  tags: tags
  properties: {
    localAuth: 'Disabled'
    regionalAffinity: 'Disabled'
  }
}

resource projectWorkspaceAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(playwrightWorkspace.id, foundryProject.id, playwrightWorkspaceContributorRoleId)
  scope: playwrightWorkspace
  properties: {
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      playwrightWorkspaceContributorRoleId
    )
  }
}

var dataplaneUri = playwrightWorkspace.properties.dataplaneUri
var playwrightMcpEndpoint = '${replace(dataplaneUri, '.api.playwright.microsoft.com', '.mcp.playwright.microsoft.com')}/mcp'

output playwrightWorkspaceName string = playwrightWorkspace.name
output playwrightWorkspaceId string = playwrightWorkspace.id
output playwrightMcpEndpoint string = playwrightMcpEndpoint
output foundryProjectPrincipalId string = foundryProject.identity.principalId