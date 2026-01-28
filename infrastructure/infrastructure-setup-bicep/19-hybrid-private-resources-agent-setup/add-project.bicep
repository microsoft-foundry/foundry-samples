@description('Location for the project resources.')
param location string = 'westus'

@description('Name of the existing AI Services account')
param existingAccountName string

@description('Resource group containing the AI Services account')
param accountResourceGroupName string = resourceGroup().name

@description('Subscription ID containing the AI Services account')
param accountSubscriptionId string = subscription().subscriptionId

@description('Name for the new project')
param projectName string

@description('Description for the new project')
param projectDescription string = 'Additional AI Foundry project with network secured deployed Agent'

@description('Display name for the new project')
param displayName string

@description('Name for the project capability host')
param projectCapHost string = 'caphostproj'

// Existing shared resources (from your original deployment)
@description('Name of the existing AI Search service')
param existingAiSearchName string

@description('Resource group containing the AI Search service')
param aiSearchResourceGroupName string

@description('Subscription ID containing the AI Search service')
param aiSearchSubscriptionId string

@description('Name of the existing Storage Account')
param existingStorageName string

@description('Resource group containing the Storage Account')
param storageResourceGroupName string

@description('Subscription ID containing the Storage Account')
param storageSubscriptionId string

@description('Name of the existing Cosmos DB account')
param existingCosmosDBName string

@description('Resource group containing the Cosmos DB account')
param cosmosDBResourceGroupName string

@description('Subscription ID containing the Cosmos DB account')
param cosmosDBSubscriptionId string

// Create a short, unique suffix for this project
param deploymentTimestamp string = utcNow('yyyyMMddHHmmss')
var uniqueSuffix = substring(uniqueString('${resourceGroup().id}-${deploymentTimestamp}'), 0, 4)
var finalProjectName = toLower('${projectName}${uniqueSuffix}')

// Reference existing AI Services account
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: existingAccountName
  scope: resourceGroup(accountSubscriptionId, accountResourceGroupName)
}

// Reference existing shared resources
resource aiSearch 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: existingAiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: existingStorageName
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
}

resource cosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: existingCosmosDBName
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
}

// Create the new project using the unique connection module
module aiProject 'modules-network-secured/ai-project-identity-unique.bicep' = {
  name: 'ai-${finalProjectName}-${uniqueSuffix}-deployment'
  params: {
    projectName: finalProjectName
    projectDescription: projectDescription
    displayName: displayName
    location: location
    
    aiSearchName: existingAiSearchName
    aiSearchServiceResourceGroupName: aiSearchResourceGroupName
    aiSearchServiceSubscriptionId: aiSearchSubscriptionId
    
    cosmosDBName: existingCosmosDBName
    cosmosDBSubscriptionId: cosmosDBSubscriptionId
    cosmosDBResourceGroupName: cosmosDBResourceGroupName
    
    azureStorageName: existingStorageName
    azureStorageSubscriptionId: storageSubscriptionId
    azureStorageResourceGroupName: storageResourceGroupName
    
    accountName: existingAccountName
    
    // Pass unique suffix for connection names
    uniqueConnectionSuffix: '-${finalProjectName}'
  }
}

module formatProjectWorkspaceId 'modules-network-secured/format-project-workspace-id.bicep' = {
  name: 'format-project-workspace-id-${uniqueSuffix}-deployment'
  params: {
    projectWorkspaceId: aiProject.outputs.projectWorkspaceId
  }
}

// Assign storage account role
module storageAccountRoleAssignment 'modules-network-secured/azure-storage-account-role-assignment.bicep' = {
  name: 'storage-${existingStorageName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    azureStorageName: existingStorageName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// Assign Cosmos DB account role
module cosmosAccountRoleAssignments 'modules-network-secured/cosmosdb-account-role-assignment.bicep' = {
  name: 'cosmos-account-ra-${finalProjectName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosDBName: existingCosmosDBName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// Assign AI Search role
module aiSearchRoleAssignments 'modules-network-secured/ai-search-role-assignments.bicep' = {
  name: 'ai-search-ra-${finalProjectName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
  params: {
    aiSearchName: existingAiSearchName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// Create capability host for the new project
module addProjectCapabilityHost 'modules-network-secured/add-project-capability-host.bicep' = {
  name: 'capabilityHost-configuration-${uniqueSuffix}-deployment'
  params: {
    accountName: existingAccountName
    projectName: aiProject.outputs.projectName
    cosmosDBConnection: aiProject.outputs.cosmosDBConnection
    azureStorageConnection: aiProject.outputs.azureStorageConnection
    aiSearchConnection: aiProject.outputs.aiSearchConnection
    projectCapHost: projectCapHost
  }
  dependsOn: [
    cosmosAccountRoleAssignments
    storageAccountRoleAssignment
    aiSearchRoleAssignments
  ]
}

// Assign storage container roles after capability host creation
module storageContainersRoleAssignment 'modules-network-secured/blob-storage-container-role-assignments-unique.bicep' = {
  name: 'storage-containers-${uniqueSuffix}-deployment'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    aiProjectPrincipalId: aiProject.outputs.projectPrincipalId
    storageName: existingStorageName
    workspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    uniqueSuffix: uniqueSuffix  // Add this line
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}

// Assign Cosmos container roles after capability host creation
module cosmosContainerRoleAssignments 'modules-network-secured/cosmos-container-role-assignments.bicep' = {
  name: 'cosmos-ra-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosAccountName: existingCosmosDBName
    projectWorkspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    addProjectCapabilityHost
    storageContainersRoleAssignment
  ]
}

// Outputs
output projectName string = aiProject.outputs.projectName
output projectPrincipalId string = aiProject.outputs.projectPrincipalId
output projectWorkspaceId string = aiProject.outputs.projectWorkspaceId
output capabilityHostName string = addProjectCapabilityHost.outputs.projectCapHost
