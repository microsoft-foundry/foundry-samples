extension microsoftGraphV1

param uniqueName string
param serviceManagementReference string = ''

var scopeId = guid(uniqueName, 'Greeting.Read')

resource application 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: uniqueName
  displayName: 'Foundry agent on behalf of user greeting MCP'
  serviceManagementReference: !empty(serviceManagementReference) ? serviceManagementReference : null
  signInAudience: 'AzureADMyOrg'
  api: {
    requestedAccessTokenVersion: 2
    oauth2PermissionScopes: [
      {
        id: scopeId
        isEnabled: true
        type: 'User'
        value: 'Greeting.Read'
        adminConsentDisplayName: 'Read greeting'
        adminConsentDescription: 'Allow the agent to request a greeting for a signed-in user.'
        userConsentDisplayName: 'Read greeting'
        userConsentDescription: 'Allow the agent to request a greeting for you.'
      }
    ]
  }
}

resource principal 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: application.appId
  appRoleAssignmentRequired: false
}

resource client 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: '${uniqueName}-client'
  displayName: 'Foundry blueprint greeting interactive client'
  serviceManagementReference: !empty(serviceManagementReference) ? serviceManagementReference : null
  signInAudience: 'AzureADMyOrg'
  isFallbackPublicClient: true
}

resource clientPrincipal 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: client.appId
  appRoleAssignmentRequired: false
}

output applicationId string = application.appId
output applicationObjectId string = application.id
output scopeId string = scopeId
output clientId string = client.appId
output clientObjectId string = client.id
