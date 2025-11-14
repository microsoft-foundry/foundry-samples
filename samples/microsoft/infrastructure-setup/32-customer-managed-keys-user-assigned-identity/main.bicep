/*
  Complete AI Foundry solution with UAI, CMK, and Project
  
  Description: 
  - Create an Azure AI Foundry account with User-Assigned Identity
  - Enable Customer-Managed Keys (CMK) encryption
  - Create a project
*/

@description('That name is the name of our application. It has to be unique.')
param aiFoundryName string = 'ai-foundry-complete-cmk'

@description('Name of the AI Foundry project')
param aiProjectName string = '${aiFoundryName}-proj'

@description('Location for all resources.')
param location string = 'eastus2'

@description('Name of the Azure Key Vault target')
param keyVaultName string

@description('Name of the Azure Key Vault key')
param keyName string

@description('Version of the Azure Key Vault key')
param keyVersion string

@description('Resource ID of the user-assigned managed identity to use for CMK encryption')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity')
param userAssignedIdentityClientId string

// Module 1: Create AI Foundry account with User-Assigned Identity
module aiFoundryAccount './modules/foundry-account.bicep' = {
  name: 'foundryAccount'
  params: {
    aiFoundryName: aiFoundryName
    location: location
    userAssignedIdentityId: userAssignedIdentityId
  }
}

// Module 2: Enable Customer-Managed Keys
module cmkEncryption './modules/cmk-encryption.bicep' = {
  name: 'cmkEncryption'
  params: {
    aiFoundryName: aiFoundryAccount.outputs.accountName
    location: location
    keyVaultName: keyVaultName
    keyName: keyName
    keyVersion: keyVersion
    userAssignedIdentityId: userAssignedIdentityId
    userAssignedIdentityClientId: userAssignedIdentityClientId
  }
}

// Module 3: Create Project
module aiProject './modules/foundry-project.bicep' = {
  name: 'foundryProject'
  params: {
    aiFoundryName: aiFoundryAccount.outputs.accountName
    projectName: aiProjectName
    projectDisplayName: aiProjectName
    projectDescription: 'AI Foundry project with customer-managed keys'
    location: location
    userAssignedIdentityId: userAssignedIdentityId
  }
  dependsOn: [
    cmkEncryption
  ]
}

output accountId string = aiFoundryAccount.outputs.accountId
output accountName string = aiFoundryAccount.outputs.accountName
output projectId string = aiProject.outputs.projectId
output projectName string = aiProject.outputs.projectName
