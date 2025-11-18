// Parameters for the application module
param accountName string
param projectName string
param applicationName string

// Application properties
param displayName string = applicationName

// Agent configuration
param agents array = []

// Reference to existing Cognitive Services account
resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

// Reference to existing Cognitive Services project
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: projectName
}

// Cognitive Services Application (child resource of project)
resource application 'Microsoft.CognitiveServices/accounts/projects/applications@2025-10-01-preview' = {
  parent: project
  name: applicationName
  properties: {
    displayName: displayName
    agents: agents
    authorizationPolicy: {
      AuthorizationScheme: 'Channels'
    }
  }
}

// Outputs
output baseUrl string = application.properties.baseUrl
output agentIdentityBlueprintId string = application.properties.agentIdentityBlueprint.clientId
