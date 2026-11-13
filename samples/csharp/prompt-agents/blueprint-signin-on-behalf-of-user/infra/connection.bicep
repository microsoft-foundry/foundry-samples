param accountName string
param projectName string
param endpoint string
param scope string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName

  resource project 'projects' existing = {
    name: projectName
  }
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: account::project
  name: 'greeting-agent-on-behalf-of-user'
  properties: {
    category: 'RemoteTool'
    target: endpoint
    #disable-next-line BCP036
    authType: 'AgentOnBehalfOfUser'
    #disable-next-line BCP037
    scopes: [
      scope
    ]
    metadata: {
      type: 'generic_mcp'
    }
  }
}

output name string = connection.name
