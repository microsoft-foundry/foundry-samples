// Run command examples:
// For existing storage account: az deployment group create --name AzDeploy --resource-group {RESOURCE_GROUP} --template-file main.bicep --parameters aiFoundryName={AI_FOUNDRY_NAME} userOwnedStorageResourceId={STORAGE_ACCOUNT_RESOURCE_ID} location={LOCATION}
// For new storage account: az deployment group create --name AzDeploy --resource-group {RESOURCE_GROUP} --template-file main.bicep --parameters aiFoundryName={AI_FOUNDRY_NAME} location={LOCATION}

@description('Name of the Azure AI Foundry account')
param aiFoundryName string

@description('Location for the resource')
param location string = resourceGroup().location

// Storage Account Parameters
@description('Azure storage resource ID (leave empty to create a new storage account)')
param userOwnedStorageResourceId string = ''

@description('Name of the Storage Account derived from the resource ID or provided for new account')
param storageAccountName string = userOwnedStorageResourceId != '' ? last(split(userOwnedStorageResourceId, '/')) : 'st${uniqueString(resourceGroup().id)}andya'

@description('Resource group name of the Storage Account derived from the resource ID')
param storageResourceGroupName string = userOwnedStorageResourceId != '' ? split(userOwnedStorageResourceId, '/')[4] : resourceGroup().name
// --------------------------------

// ====================================================================
// DEPLOYMENT STEPS OVERVIEW:
// 1. Collect user info for Storage Account, if it exists 
// 2. Check if Storage Account exists 
// 3. Create Storage Account (if not using existing one) 
// 4. Create AI Foundry with User Owned Storage 
// 5. Create Role Assignment for AI Foundry's managed identity on the Storage Account
// ====================================================================

// ====================================================================
// STEP 1: STORAGE ACCOUNT CONFIGURATION
// ====================================================================
@description('Automatically determined based on whether userOwnedStorageResourceId is provided')
var useExistingStorageAccount bool = userOwnedStorageResourceId != ''

// ====================================================================
// STEP 2: CHECK IF STORAGE ACCOUNT EXISTS
// ====================================================================
resource existingStorageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' existing = if (useExistingStorageAccount) {
  name: storageAccountName
  scope: resourceGroup(storageResourceGroupName)
}

// ====================================================================
// STEP 3: CREATE STORAGE ACCOUNT (IF NOT USING EXISTING ONE)
// ====================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = if (!useExistingStorageAccount) {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_RAGRS'
  }
  kind: 'StorageV2'
  properties: {
    // For Azure AI Foundry BYOS, these settings are required
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true  // Must be true for AI Foundry to access
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    // Required for AI Foundry BYOS
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: false
  }
}

// ====================================================================
// STEP 4: CREATE AI FOUNDRY WITH USER OWNED STORAGE
// ====================================================================
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-07-01-preview' = {
  name: aiFoundryName
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
    publicNetworkAccess: 'Enabled' // or 'Disabled' 
    disableLocalAuth: false
    customSubDomainName: toLower(replace(aiFoundryName, '_', '-'))
    userOwnedStorage: [{
        resourceId: useExistingStorageAccount ? existingStorageAccount.id : storageAccount.id
    }]
  }
}

// ====================================================================
// STEP 5: CREATE ROLE ASSIGNMENT FOR AI FOUNDRY'S MANAGED IDENTITY
// ====================================================================
// Using module to handle role assignment for both existing and new storage accounts
module roleAssignmentModule './modules/roleAssignment.bicep' = {
  name: 'storageRoleAssignment'
  scope: resourceGroup(storageResourceGroupName)
  params: {
    storageAccountName: storageAccountName
    principalId: aiFoundry.identity.principalId
    aiFoundryResourceId: aiFoundry.id
  }
}

// ====================================================================
// OUTPUTS
// ====================================================================
@description('The resource ID of the AI Foundry account')
output aiFoundryId string = aiFoundry.id

@description('The name of the AI Foundry account')
output aiFoundryName string = aiFoundry.name

@description('The resource ID of the storage account being used')
output storageAccountId string = useExistingStorageAccount ? existingStorageAccount.id : storageAccount.id

@description('The managed identity principal ID of the AI Foundry account')
output aiFoundryPrincipalId string = aiFoundry.identity.principalId

@description('Status of role assignment')
output roleAssignmentStatus string = 'Storage Blob Data Contributor role assigned automatically via module'
