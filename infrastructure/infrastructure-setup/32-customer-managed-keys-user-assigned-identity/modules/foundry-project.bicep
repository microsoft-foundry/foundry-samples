/*
  Module: AI Foundry Project Creation
  
  Creates a project under the AI Foundry account:
  - Project with user-assigned identity inheritance
  - Display name and description configuration
*/

@description('Name of the AI Foundry account (parent)')
param aiFoundryName string

@description('Location for the resource')
param location string

@description('Name of the project')
param projectName string

@description('Display name for the project')
param projectDisplayName string

@description('Description for the project')
param projectDescription string

@description('Resource ID of the user-assigned managed identity')
param userAssignedIdentityId string

// Reference the existing AI Foundry account
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
}

// Create the project under the AI Foundry account
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  name: projectName
  parent: account
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    displayName: projectDisplayName
    description: projectDescription
  }
}

// Outputs
output projectId string = project.id
output projectName string = project.name