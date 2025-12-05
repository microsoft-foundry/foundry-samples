targetScope = 'resourceGroup'

// =================================================================================================
// Main parameters
// =================================================================================================

@minLength(1)
@maxLength(64)
@description('Name of the application. Used to ensure resource names are unique.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

// =================================================================================================
// Project module parameters
// =================================================================================================

@description('Name of the Cognitive Services account')
param accountName string = '${environmentName}acct'

@description('Name of the Cognitive Services project')
param projectName string = '${environmentName}proj'

@description('Name of the Container Registry')
param containerRegistryName string = '${environmentName}acr'

@description('SKU of Cognitive Services account')
param cognitiveServicesSku string = 'S0'

@description('SKU of Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param containerRegistrySku string = 'Basic'

// =================================================================================================
// Application module parameters
// =================================================================================================

@description('Name of the Cognitive Services application')
param applicationName string = '${environmentName}app'

@description('Display name of the application')
param applicationDisplayName string = '${environmentName} Application'

param agentName string = 'foundry-agent'

@description('Agents configuration for the application')
param agents array = [
  {
    agentId: '$azureml://tenants/${tenant().tenantId}/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/accounts/${accountName}/projects/${projectName}/${agentName}'
    agentName: agentName
  }
]

// =================================================================================================
// Bot Service module parameters
// =================================================================================================

@description('Name of the Bot Service')
param botName string = '${environmentName}bot'

@description('Display name of the bot')
param botDisplayName string = '${environmentName} Bot'

@description('SKU of the Bot Service')
param botServiceSku string = 'F0'

// =================================================================================================
// Common parameters
// =================================================================================================

@description('Tags to apply to all resources')
param tags object = {}

// =================================================================================================
// Module deployments
// =================================================================================================

// 1. Deploy the project module (Cognitive Services account, project, and Container Registry)
module project 'modules/project.bicep' = {
  name: 'project-deployment'
  params: {
    accountName: accountName
    projectName: projectName
    containerRegistryName: containerRegistryName
    location: location
    tags: tags
    cognitiveServicesSku: cognitiveServicesSku
    containerRegistrySku: containerRegistrySku
  }
}

// 2. Create deployment script UMI and grant roles on RG.
module deploymentScriptUmi 'modules/deployment-script-umi.bicep' = {
  name: 'deployment-script-umi'
  dependsOn: [
    project
  ]
}

// 3. Create agent definition as deployment script.
module deploymentScriptAgent 'modules/agent-deployment-script.bicep' = {
  name: 'agent-deployment-script'
  params: {
    uamiResourceId: deploymentScriptUmi.outputs.uamiResourceId
    azureAIProjectEndpoint: project.outputs.foundryProjectEndpoint
    agentName: agentName
    azureContainerRegistryEndpoint: project.outputs.acrloginServer
  }
  dependsOn: [
    deploymentScriptUmi
  ]
}


// 4. Deploy the application module (depends on project)
module application 'modules/application.bicep' = {
  name: 'application-deployment'
  params: {
    accountName: accountName
    projectName: projectName
    applicationName: applicationName
    displayName: applicationDisplayName
    agents: agents
  }
  dependsOn: [
    deploymentScriptAgent
  ]
}

// 5. Deploy the bot service module
module botService 'modules/botservice.bicep' = {
  name: 'botservice-deployment'
  params: {
    botName: botName
    displayName: botDisplayName
    msaAppId: application.outputs.agentIdentityBlueprintId
    endpoint: 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}/applications/${applicationName}/protocols/activityprotocol?api-version=2025-05-15-preview'
    botServiceSku: botServiceSku
  }
  dependsOn: [
    application
  ]
}

// =================================================================================================
// Outputs - These become environment variables in post-provision.sh
// =================================================================================================

@description('ACR login server endpoint')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = project.outputs.acrloginServer

output AZURE_AI_PROJECT_ENDPOINT string = project.outputs.foundryProjectEndpoint

@description('Agent identity blueprint ID')
output AGENT_IDENTITY_BLUEPRINT_ID string = application.outputs.agentIdentityBlueprintId

@description('Application name')
output APPLICATION_NAME string = applicationName

output SUBSCRIPTION_ID string = subscription().subscriptionId

output LOCATION string = location

output ACCOUNT_NAME string = accountName

output PROJECT_NAME string = projectName

output AGENT_NAME string = agentName

output TENANT_ID string = tenant().tenantId

output PROJECT_PRINCIPAL_ID string = project.outputs.foundryProjectPrincipalId
