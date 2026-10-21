targetScope = 'subscription'

@description('Name of the resource group created by the Microsoft Foundry layer.')
param resourceGroupName string

@description('Name of the Microsoft Foundry account.')
param accountName string

@description('Name of the Microsoft Foundry project.')
param projectName string

@description('Name of the azd environment.')
param environmentName string

@description('Location for the Playwright workspace.')
param playwrightLocation string

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: resourceGroupName
}

module resources './resources.bicep' = {
  name: 'browser-automation-resources'
  scope: resourceGroup
  params: {
    accountName: accountName
    projectName: projectName
    environmentName: environmentName
    playwrightLocation: playwrightLocation
    tags: {
      'azd-env-name': environmentName
    }
  }
}

output PLAYWRIGHT_WORKSPACE_NAME string = resources.outputs.playwrightWorkspaceName
output PLAYWRIGHT_WORKSPACE_ID string = resources.outputs.playwrightWorkspaceId
output PLAYWRIGHT_MCP_ENDPOINT string = resources.outputs.playwrightMcpEndpoint
output FOUNDRY_PROJECT_PRINCIPAL_ID string = resources.outputs.foundryProjectPrincipalId