/*
  AI Foundry account and project - with your User-Assigned managed identity.
  
  Description: 
  - Creates an AI Foundry (previously known as Azure AI Services) account and project with UAI.
  - Creates a gpt-4o model deployment
  - Creates workspace-based Application Insights and connects it to the project

  Known limitations:
  - When creating a project, managed identity cannot be updated. Please select 'SystemAssigned', 'UserAssigned' or 'SystemAssigned,UserAssigned' during creation.
  - Only one Application Insights connection can be configured on a project.

*/
@description('That name is the name of our application. It has to be unique. Type a name followed by your resource group name. (<name>-<resourceGroupName>)')
param aiFoundryName string = 'foundry-uai'

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Name of the first project')
param defaultProjectName string = '${aiFoundryName}-proj'
/*
  Step 1: Create or reference a user-assigned managed identity
*/
@description('Resource group containing an existing user-assigned managed identity. Leave empty to create the identity.')
param userIdentityResourceGroupName string = ''

@description('Name of the user-assigned managed identity.')
param userAssignedIdentityName string = '${aiFoundryName}-uai'

@description('Name of the Log Analytics workspace used by Application Insights.')
param logAnalyticsWorkspaceName string = take('${aiFoundryName}-law', 63)

@description('Name of the Application Insights component connected to the project.')
param applicationInsightsName string = '${aiFoundryName}-appi'

@description('Name of the Application Insights connection on the project.')
param applicationInsightsConnectionName string = '${applicationInsightsName}-connection'

@description('Use the project managed identity for trace ingestion. This authentication mode is currently in preview.')
param useProjectManagedIdentityForTraceIngestion bool = false

@description('Share the Application Insights connection with all project users.')
param isApplicationInsightsConnectionSharedToAll bool = true

@description('Deploy the GPT-4o model. No model is deployed by default.')
param deployModel bool = false

var useExistingUserAssignedIdentity = !empty(userIdentityResourceGroupName)

resource existingUserAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-07-31-preview' existing = if (useExistingUserAssignedIdentity) {
  name: userAssignedIdentityName
  scope: resourceGroup(userIdentityResourceGroupName)
}

resource newUserAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-07-31-preview' = if (!useExistingUserAssignedIdentity) {
  name: userAssignedIdentityName
  location: location
}

var userAssignedIdentityId = useExistingUserAssignedIdentity ? existingUserAssignedIdentity.id : newUserAssignedIdentity.id
var userAssignedIdentityPrincipalId = useExistingUserAssignedIdentity ? existingUserAssignedIdentity!.properties.principalId : newUserAssignedIdentity!.properties.principalId

/*
  Step 2: Create a Cognitive Services Account 
*/ 
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiFoundryName
  location: location
  identity: {
    type: 'UserAssigned' // Select 'UserAssigned' or 'SystemAssigned,UserAssigned' during creation as this cannot be updated.
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // Networking
    publicNetworkAccess: 'Enabled'

    // Specifies whether this resource support project management as child resources, used as containers for access management, data isolation, and cost in AI Foundry.
    allowProjectManagement: true

    // Defines developer API endpoint subdomain
    customSubDomainName: aiFoundryName

    // Auth
    disableLocalAuth: false
  }
}

/*
  Step 3: Deploy gpt-4o model
*/
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01'= if (deployModel) {
  parent: account
  name: 'gpt-4o'
  sku : {
    capacity: 1
    name: 'GlobalStandard'
  }
  properties: {
    model:{
      name: 'gpt-4o'
      format: 'OpenAI'
      version: '2024-08-06'
    }
  }
}

/*
  Step 4: Create a Project
*/
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: defaultProjectName
  parent: account
  location: location
  
  identity: {
    type: 'UserAssigned' // Select 'UserAssigned' or 'SystemAssigned,UserAssigned' during creation as this cannot be updated.
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  
  properties: {}
}

/*
  Step 5: Create workspace-based Application Insights
*/
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    DisableLocalAuth: useProjectManagedIdentityForTraceIngestion
  }
}

var monitoringMetricsPublisherRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '3913510d-42f4-4e42-8a64-420c390055eb'
)

var applicationInsightsReaderRoleDefinitionIds = [
  subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893') // Log Analytics Reader
  subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'dbc9c667-e97f-4491-aee6-90b9cf960190') // Privileged Monitoring Data Reader
]

resource monitoringMetricsPublisherRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (useProjectManagedIdentityForTraceIngestion) {
  name: guid(userAssignedIdentityId, monitoringMetricsPublisherRoleDefinitionId, applicationInsights.id)
  scope: applicationInsights
  properties: {
    principalId: userAssignedIdentityPrincipalId
    roleDefinitionId: monitoringMetricsPublisherRoleDefinitionId
    principalType: 'ServicePrincipal'
  }
}

resource applicationInsightsReaderRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleDefinitionId in applicationInsightsReaderRoleDefinitionIds: {
  name: guid(userAssignedIdentityId, roleDefinitionId, applicationInsights.id)
  scope: applicationInsights
  properties: {
    principalId: userAssignedIdentityPrincipalId
    roleDefinitionId: roleDefinitionId
    principalType: 'ServicePrincipal'
  }
}]

/*
  Step 6: Connect Application Insights to the project
*/
resource applicationInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-09-01' = {
  name: applicationInsightsConnectionName
  parent: project
  properties: union({
    category: 'AppInsights'
    target: applicationInsights.id
    authType: useProjectManagedIdentityForTraceIngestion ? 'ProjectManagedIdentity' : 'ApiKey'
    isSharedToAll: isApplicationInsightsConnectionSharedToAll
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
      ApplicationInsightsConnectionString: applicationInsights.properties.ConnectionString
    }
  }, useProjectManagedIdentityForTraceIngestion ? {} : {
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
  })
}

output accountId string = account.id
output accountName string = account.name
output project string = project.name
output applicationInsightsId string = applicationInsights.id
output applicationInsightsAppId string = applicationInsights.properties.AppId
output deployedApplicationInsightsConnectionName string = applicationInsightsConnection.name
output applicationInsightsConnectionAuthType string = useProjectManagedIdentityForTraceIngestion ? 'ProjectManagedIdentity' : 'ApiKey'
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
