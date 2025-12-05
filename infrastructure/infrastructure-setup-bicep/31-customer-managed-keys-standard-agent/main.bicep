// Standard agent setup 

@description('The region to deploy your AI Services resource and project')
param location string = 'eastus2'

@description('Name for your AI Services resource.')
param aiFoundryName string = 'aifstdcmk4'

@description('Name for your project resource.')
param projectName string = 'project'

@description('Name of the Azure Key Vault target')
param keyVaultName string = '<your-key-vault>'

@description('Name of the Azure Key Vault key')
param keyName string = '<your-key>'

@description('Version of the Azure Key Vault key')
param keyVersion string = '<your-key-version>'

var keyVaultUri = 'https://${keyVaultName}.vault.azure.net/'
var keyVaultKeyUri = '${keyVaultUri}keys/${keyName}'

@description('The AI Search Service full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param aiSearchResourceId string = ''

@description('The AI Storage Account full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param azureStorageAccountResourceId string = ''
@description('The Cosmos DB Account full ARM Resource ID. This is an optional field, and if not provided, the resource will be created.')
param azureCosmosDBAccountResourceId string = ''

param projectCapHost string = 'caphostproj'
param accountCapHost string = 'caphostacc'

// Create a short, unique suffix, that will be unique to each resource group
param deploymentTimestamp string = utcNow('yyyyMMddHHmmss')

var uniqueSuffix = substring(uniqueString('${resourceGroup().id}-${deploymentTimestamp}'), 0, 4)

var accountName = toLower('${aiFoundryName}${uniqueSuffix}')

var cosmosDBName = toLower('${aiFoundryName}${uniqueSuffix}cosmosdb')
var aiSearchName = toLower('${aiFoundryName}${uniqueSuffix}search')
var azureStorageName = toLower('${aiFoundryName}${uniqueSuffix}storage')

// Check if existing resources have been passed in
var storagePassedIn = azureStorageAccountResourceId != ''
var searchPassedIn = aiSearchResourceId != ''
var cosmosPassedIn = azureCosmosDBAccountResourceId != ''

var acsParts = split(aiSearchResourceId, '/')
var aiSearchServiceSubscriptionId = searchPassedIn ? acsParts[2] : subscription().subscriptionId
var aiSearchServiceResourceGroupName = searchPassedIn ? acsParts[4] : resourceGroup().name

var cosmosParts = split(azureCosmosDBAccountResourceId, '/')
var cosmosDBSubscriptionId = cosmosPassedIn ? cosmosParts[2] : subscription().subscriptionId
var cosmosDBResourceGroupName = cosmosPassedIn ? cosmosParts[4] : resourceGroup().name

var storageParts = split(azureStorageAccountResourceId, '/')
var azureStorageSubscriptionId = storagePassedIn ? storageParts[2] : subscription().subscriptionId
var azureStorageResourceGroupName = storagePassedIn ? storageParts[4] : resourceGroup().name

/*
  Validate existing resources
  This module will check if the AI Search Service, Storage Account, and Cosmos DB Account already exist.
  If they do, it will set the corresponding output to true. If they do not exist, it will set the output to false.
*/
module validateExistingResources 'modules-standard/validate-existing-resources.bicep' = {
  name: 'validate-existing-resources-${uniqueSuffix}-deployment'
  params: {
    aiSearchResourceId: aiSearchResourceId
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureCosmosDBAccountResourceId: azureCosmosDBAccountResourceId
  }
}

/*
  Create the AI Services account and gpt-4o model deployment
*/
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
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'

    // API-key based auth is not supported for the Agent service
    disableLocalAuth: false
  }
}

// This module will create new agent dependent resources
// A Cosmos DB account, an AI Search Service, and a Storage Account are created if they do not already exist
module aiDependencies 'modules-standard/standard-dependent-resources.bicep' = {
  name: 'dependencies-${accountName}-${uniqueSuffix}-deployment'
  params: {
    location: location
    azureStorageName: azureStorageName
    aiSearchName: aiSearchName
    cosmosDBName: cosmosDBName

    // AI Search Service parameters
    aiSearchResourceId: aiSearchResourceId
    aiSearchExists: validateExistingResources.outputs.aiSearchExists

    // Storage Account
    azureStorageAccountResourceId: azureStorageAccountResourceId
    azureStorageExists: validateExistingResources.outputs.azureStorageExists

    // Cosmos DB Account
    cosmosDBResourceId: azureCosmosDBAccountResourceId
    cosmosDBExists: validateExistingResources.outputs.cosmosDBExists

    keyVaultUri: keyVaultUri
    keyVaultkey: keyVersion
    keyVaultKeyUri: keyVaultKeyUri
  }
}

// Set up customer-managed key encryption once managed identity has been created
module encryptionUpdate 'modules-standard/ai-account-encryption.bicep' = {
  name: 'updateEncryption'
  params: {
    aiFoundryName: account.name
    aiFoundryPrincipal: account.identity.principalId
    keyVaultName: keyVaultName
    location: location
    keyVaultUri: keyVaultUri
    keyName: keyName
    keyVersion: keyVersion
  }
  dependsOn: [
    aiDependencies
  ]
}

/*
  Creates a new project (sub-resource of the AI Services account)
*/
module aiProject 'modules-standard/ai-project-identity.bicep' = {
  name: 'ai-${projectName}-${uniqueSuffix}-deployment'
  params: {
    projectName: projectName
    projectDescription: 'Describe your project'
    displayName: projectName
    location: location

    aiSearchName: aiDependencies.outputs.aiSearchName
    aiSearchServiceResourceGroupName: aiDependencies.outputs.aiSearchServiceResourceGroupName
    aiSearchServiceSubscriptionId: aiDependencies.outputs.aiSearchServiceSubscriptionId

    cosmosDBName: aiDependencies.outputs.cosmosDBName
    cosmosDBSubscriptionId: aiDependencies.outputs.cosmosDBSubscriptionId
    cosmosDBResourceGroupName: aiDependencies.outputs.cosmosDBResourceGroupName

    azureStorageName: aiDependencies.outputs.azureStorageName
    azureStorageSubscriptionId: aiDependencies.outputs.azureStorageSubscriptionId
    azureStorageResourceGroupName: aiDependencies.outputs.azureStorageResourceGroupName
    
    accountName: account.name
  }
  dependsOn: [
    encryptionUpdate
  ]
}

/*
  Assigns the project SMI the storage blob data contributor role on the storage account
*/
module storageAccountRoleAssignment 'modules-standard/azure-storage-account-role-assignment.bicep' = {
  name: 'storage-${azureStorageName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
  params: { 
    azureStorageName: aiDependencies.outputs.azureStorageName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// The Comos DB Operator role must be assigned before the caphost is created
module cosmosAccountRoleAssignments 'modules-standard/cosmosdb-account-role-assignment.bicep' = {
  name: 'cosmos-account-role-assignments-${projectName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosDBName: aiDependencies.outputs.cosmosDBName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    storageAccountRoleAssignment
  ]

}

// This role can be assigned before or after the caphost is created
module aiSearchRoleAssignments 'modules-standard/ai-search-role-assignments.bicep' = {
  name: 'ai-search-role-assignments-${projectName}-${uniqueSuffix}-deployment'
  scope: resourceGroup(aiSearchServiceSubscriptionId, aiSearchServiceResourceGroupName)
  params: {
    aiSearchName: aiDependencies.outputs.aiSearchName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn:[
    cosmosAccountRoleAssignments, storageAccountRoleAssignment
  ]
}

module addProjectCapabilityHost 'modules-standard/add-project-capability-host.bicep' = {
  name: 'capabilityHost-configuration-${projectName}-${uniqueSuffix}-deployment'
  params: {
    accountName: account.name
    projectName: aiProject.outputs.projectName
    cosmosDBConnection: aiProject.outputs.cosmosDBConnection 
    azureStorageConnection: aiProject.outputs.azureStorageConnection
    aiSearchConnection: aiProject.outputs.aiSearchConnection

    projectCapHost: projectCapHost
    accountCapHost: accountCapHost
  }
  dependsOn: [
    aiSearchRoleAssignments, cosmosAccountRoleAssignments, storageAccountRoleAssignment
  ]
}

module cosmosContainerRoleAssignments 'modules-standard/cosmos-container-role-assignments.bicep' = {
  name: 'cosmos-role-assignments-${uniqueSuffix}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosAccountName: aiDependencies.outputs.cosmosDBName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}

// The Storage Blob Data Owner role must be assigned before the caphost is created
module storageContainersRoleAssignment 'modules-standard/blob-storage-container-role-assignments.bicep' = {
  name: 'storage-containers-${uniqueSuffix}-deployment'
  scope: resourceGroup(azureStorageSubscriptionId, azureStorageResourceGroupName)
  params: { 
    aiProjectPrincipalId: aiProject.outputs.projectPrincipalId
    storageName: aiDependencies.outputs.azureStorageName
    workspaceId: aiProject.outputs.projectId
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}
