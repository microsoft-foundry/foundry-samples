// Basic agent setup 
@description('The name of the Azure AI Foundry resource.')
@maxLength(60)
param aiServicesName string = 'foundy'

@description('The name of your project')
param projectName string = 'project'

@description('The description of your project')
param projectDescription string = 'some description'

@description('The display name of your project')
param projectDisplayName string = 'project_display_name'

//ensures unique name for the account
// Create a short, unique suffix, that will be unique to each resource group
param deploymentTimestamp string = utcNow('yyyyMMddHHmmss')
var uniqueSuffix = substring(uniqueString('${resourceGroup().id}-${deploymentTimestamp}'), 0, 4)
var accountName = toLower('${aiServicesName}${uniqueSuffix}')

@description('Deploy a Log Analytics workspace + Application Insights, connect them to the Foundry account, and grant the project managed identity read access so agent traces can be viewed and evaluated. Adds resources/cost. Default true.')
param deployApplicationInsights bool = true

var appInsightsName = toLower('${uniqueSuffix}appinsights')
var logAnalyticsName = toLower('${uniqueSuffix}loganalytics')
@allowed([
  'australiaeast'
  'canadaeast'
  'eastus'
  'eastus2'
  'francecentral'
  'japaneast'
  'koreacentral'
  'norwayeast'
  'polandcentral'
  'southindia'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westus'
  'westus2'
  'westus3'
  'westeurope'
  'southeastasia'
  'brazilsouth'
  'germanywestcentral'
  'italynorth'
  'southafricanorth'
  'southcentralus'
])
@description('The Azure region where your AI Foundry resource and project will be created.')
param location string = 'eastus'

@description('The name of the OpenAI model you want to deploy')
param modelName string = 'gpt-4.1'

@description('The model format of the model you want to deploy. Example: OpenAI')
param modelFormat string = 'OpenAI'

@description('The version of the model you want to deploy. Example: 2024-11-20')
param modelVersion string = '2025-04-14'

@description('The SKU name for the model deployment. Example: GlobalStandard')
param modelSkuName string = 'GlobalStandard'

@description('The capacity of the model deployment in TPM.')
param modelCapacity int = 40

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: toLower(accountName)
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

/*
  Step 2: Deploy gpt-4o model
  
  - Agents will use the build-in model deployments
*/ 



/*
  Step 3: Create a Cognitive Services Project
    
*/
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectDisplayName
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01'= {
  parent: account
  name: modelName
  sku : {
    capacity: modelCapacity
    name: modelSkuName
  }
  properties: {
    model:{
      name: modelName
      format: modelFormat
      version: modelVersion
    }
  }
}

// Application Insights + Foundry connection (agent tracing), gated by deployApplicationInsights
module applicationInsights 'modules-basic/application-insights.bicep' = if (deployApplicationInsights) {
  name: 'app-insights-${uniqueSuffix}-deployment'
  params: {
    location: location
    aiAccountName: account.name
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
  }
  dependsOn: [
    project
  ]
}

module applicationInsightsRoleAssignment 'modules-basic/application-insights-role-assignment.bicep' = if (deployApplicationInsights) {
  name: 'app-insights-ra-${uniqueSuffix}-deployment'
  params: {
    appInsightsName: appInsightsName
    projectPrincipalId: project.identity.principalId
  }
  dependsOn: [
    applicationInsights
  ]
}

output accountName string = account.name
output projectName string = project.name
output accountEndpoint string = account.properties.endpoint
output applicationInsightsResourceId string = deployApplicationInsights ? applicationInsights.outputs.appInsightsId : ''
output applicationInsightsAppId string = deployApplicationInsights ? applicationInsights.outputs.appInsightsAppId : ''
output logAnalyticsWorkspaceId string = deployApplicationInsights ? applicationInsights.outputs.logAnalyticsId : ''
