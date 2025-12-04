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
param storageAccountName string = userOwnedStorageResourceId != '' ? last(split(userOwnedStorageResourceId, '/')) : 'st${uniqueString(subscription().subscriptionId, resourceGroup().name)}aaviles' // no '-' allowed

@description('Resource group name of the Storage Account derived from the resource ID or same as AI Foundry for new accounts')
param storageResourceGroupName string = userOwnedStorageResourceId != '' ? split(userOwnedStorageResourceId, '/')[4] : resourceGroup().name

// Derived values for cross-subscription support
var targetStorageSubscriptionId = userOwnedStorageResourceId != '' ? split(userOwnedStorageResourceId, '/')[2] : subscription().subscriptionId
// --------------------------------

// ====================================================================
// DEPLOYMENT STEPS OVERVIEW:
// 1. Storage Account Configuration (existing vs new)
// 2. Create Storage Account (if new - always in same RG as AI Foundry)
// 3. Create AI Foundry with User Owned Storage 
// 4. Create Role Assignment for AI Foundry's managed identity on the Storage Account
// ====================================================================

// ====================================================================
// STEP 1: STORAGE ACCOUNT CONFIGURATION
// ====================================================================
@description('Automatically determined based on whether userOwnedStorageResourceId is provided')
var useExistingStorageAccount bool = userOwnedStorageResourceId != ''

// ====================================================================
// STEP 2: CREATE STORAGE ACCOUNT (IF NOT USING EXISTING ONE)
// ====================================================================
// New storage accounts are always created in the same resource group as AI Foundry
// For cross-subscription existing storage, we use the target subscription for role assignment

// For cross-subscription storage account creation (not recommended, but supported)
module storageAccountModule './modules/storageAccount.bicep' = if (!useExistingStorageAccount && targetStorageSubscriptionId != subscription().subscriptionId) {
  name: 'crossSubStorageAccount'
  scope: resourceGroup(targetStorageSubscriptionId, resourceGroup().name)
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

// For same-subscription storage account creation (recommended)
resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = if (!useExistingStorageAccount && targetStorageSubscriptionId == subscription().subscriptionId) {
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
// STEP 3: CREATE AI FOUNDRY WITH USER OWNED STORAGE
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
        resourceId: useExistingStorageAccount ? userOwnedStorageResourceId : '/subscriptions/${targetStorageSubscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.Storage/storageAccounts/${storageAccountName}'
    }]
  }
}

// ====================================================================
// STEP 4: CREATE ROLE ASSIGNMENT FOR AI FOUNDRY'S MANAGED IDENTITY
// ====================================================================
// Role assignment deployed to the correct subscription/resource group based on storage location
module roleAssignmentModule './modules/roleAssignment.bicep' = {
  name: 'storageRoleAssignment'
  scope: resourceGroup(targetStorageSubscriptionId, storageResourceGroupName)
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
output storageAccountId string = useExistingStorageAccount ? userOwnedStorageResourceId : '/subscriptions/${targetStorageSubscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.Storage/storageAccounts/${storageAccountName}'

@description('The managed identity principal ID of the AI Foundry account')
output aiFoundryPrincipalId string = aiFoundry.identity.principalId

@description('The subscription ID where the storage account is located')
output storageSubscriptionId string = targetStorageSubscriptionId

@description('Status of role assignment')
output roleAssignmentStatus string = 'Storage Blob Data Contributor role assigned automatically via module'
