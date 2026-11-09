@description('Name of the existing Microsoft Foundry account.')
param accountName string

@description('Name of the existing Microsoft Foundry project.')
param projectName string

resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: aiFoundry
  name: projectName
}

resource workiqMailConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: foundryProject
  name: 'WorkIQMail'
  properties: any({
    category: 'RemoteTool'
    target: 'https://agent365.svc.cloud.microsoft/agents/servers/mcp_MailTools'
    authType: 'UserEntraToken'
    audience: 'ea9ffc3e-8a23-4a7d-836d-234d7c7565c1'
    isSharedToAll: false
    metadata: {
      toolEntityId: 'azureml://location/eastus/apiCenter/registry-prod-bl/type/tools/objectId/microsoft-outlook-mail-mcp-frontier/version/1'
      type: 'catalog_MCP'
    }
  })
}

resource workiqUserConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: foundryProject
  name: 'WorkIQUser'
  properties: any({
    category: 'RemoteTool'
    target: 'https://agent365.svc.cloud.microsoft/agents/servers/mcp_MeServer'
    authType: 'UserEntraToken'
    audience: 'ea9ffc3e-8a23-4a7d-836d-234d7c7565c1'
    isSharedToAll: false
    metadata: {
      toolEntityId: 'azureml://location/eastus/apiCenter/registry-prod-bl/type/tools/objectId/microsoft-365-user-profile-mcp-frontier/version/1'
      type: 'catalog_MCP'
    }
  })
}
