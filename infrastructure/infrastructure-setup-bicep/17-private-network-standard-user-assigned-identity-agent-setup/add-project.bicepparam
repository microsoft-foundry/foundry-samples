using './add-project.bicep'

param location = 'westus'

// New project details
param projectName = 'secondproject'
param projectDescription = 'Second AI Foundry project with network secured deployed Agent'
param displayName = 'Second Project'
param projectCapHost = 'caphostsecond'

// Existing AI Services account details (from your original deployment)
// You'll need to get these from your existing deployment
param existingAccountName = '' // Replace with your actual account name
param accountResourceGroupName = '' // Your resource group
param accountSubscriptionId = ''

// Existing shared resources (from your original deployment)
// You'll need to get these from your existing deployment outputs
param existingAiSearchName = '' // Replace with your actual search service name
param aiSearchResourceGroupName = '' // Your resource group
param aiSearchSubscriptionId = ''

param existingStorageName = '' // Replace with your actual storage account name
param storageResourceGroupName = '' // Your resource group
param storageSubscriptionId = ''

param existingCosmosDBName = '' // Replace with your actual Cosmos DB name
param cosmosDBResourceGroupName = '' // Your resource group
param cosmosDBSubscriptionId = ''

// Existing User Assigned Identity details (from your original deployment)
// You'll need to get these from your existing deployment outputs
param existingUserAssignedIdentityName = '' // Replace with your actual user assigned identity name
param userAssignedIdentityResourceGroupName = '' // Your resource group
param userAssignedIdentitySubscriptionId = '' // Your subscription ID
