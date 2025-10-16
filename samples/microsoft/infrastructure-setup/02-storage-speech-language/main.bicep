// Run command: az deployment group create --name AzDeploy --resource-group {RESOURCE_GROUP} --template-file main.bicep --parameters aiFoundryName={AI_FOUNDRY_NAME} userOwnedStorageResourceId={STORAGE_ACCOUNT_RESOURCE_ID} location={LOCATION}

@description('Name of the Azure AI Foundry account')
param aiFoundryName string

@description('Location for the resource')
param location string = resourceGroup().location

// Storage Account Parameters
@description('Azure storage resource ID')
param userOwnedStorageResourceId string

@description('Name of the Storage Account derived from the resource ID')
param storageAccountName string = last(split(userOwnedStorageResourceId, '/'))

@description('Resource group name of the Storage Account derived from the resource ID')
param storageResourceGroupName string = split(userOwnedStorageResourceId, '/')[4]
// --------------------------------

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
    allowProjectManagement: false
    publicNetworkAccess: 'Enabled' //'Disabled' 
    disableLocalAuth: false
    //customSubDomainName: toLower(replace(aiFoundryName, '_', '-'))
    userOwnedStorage: [
		{
        resourceId: userOwnedStorageResourceId
		}
  ]
  }
}


// Create a role assignment on the Storage account for the AI Foundry's managed identity
module roleAssignmentModule './modules/roleAssignment.bicep' = {
  name: 'storageRoleAssignment'
  scope: resourceGroup(storageResourceGroupName)
  params: {
    storageAccountName: storageAccountName
    principalId: aiFoundry.identity.principalId
    aiFoundryResourceId: aiFoundry.id
  }
}
