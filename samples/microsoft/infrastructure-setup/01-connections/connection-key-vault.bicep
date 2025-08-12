/*

Set up your Key Vault connection

Select which RBAC role to assign:
1. Key Vault Administrator:  00482a5a-887f-4fb3-b363-3b7fe8e74483 - https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/security#key-vault-administrator
2. Key Vault Contributor:    f25e0fa2-a7c8-4377-a976-54943a77a395 - https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/security#key-vault-contributor
3. Key Vault Secret Officer: b86a8fe4-44ce-4948-aee5-eccb2c155cd7 - https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/security#key-vault-secrets-officer
This template defaults to using the Key Vault Secret Officer role.


Run command:
az deployment group create \
  --name AzDeploy \
  --resource-group {RESOURCE-GROUP-NAME} \
  --template-file connection-key-vault.bicep \
  --parameters aiFoundryName={Foundry-resource-name} connectedResourceName={KV-resource-name}

az deployment group create --name AzDeploY --resource-group {RESOURCE-GROUP-NAME} --template-file connection-key-vault.bicep --parameters aiFoundryName={Foundry-resource-name} connectedResourceName={KV-resource-name}

*/

param aiFoundryName string = '<your-account-name>'
param connectedResourceName string = 'ais-${aiFoundryName}'
//param resourceGroupName string = '<your-resource-group-name>'


resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Conditionally refers your existing Azure Key Vault resource
resource existingKeyVault 'Microsoft.KeyVault/vaults@2024-11-01' existing = {
  name: connectedResourceName
  scope: resourceGroup()
}

resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-keyvault'
  parent: aiFoundry
  properties: {
    category: 'AzureKeyVault'
    target: existingKeyVault.id
    authType: 'ProjectManagedIdentity' // should be "ResourceManagedIdentity"
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: existingKeyVault.id
      location: existingKeyVault.location
    }
  }
}

// Include RBAC on Key Vault for Foundry
resource rbacAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(existingKeyVault.id, 'KeyVaultSecretsOfficer')
  scope: existingKeyVault
  properties: {
    roleDefinitionId: '/providers/Microsoft.Authorization/roleDefinitions/b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
    principalId: aiFoundry.identity.principalId
  }
}

// Create a new connection

param location string = 'eastus'

@allowed([
  'new'
  'existing'
])
param newOrExisting string = 'new'

// Conditionally refers your existing Azure AI Search resource
resource existingAppInsights 'Microsoft.Insights/components@2020-02-02' existing = if (newOrExisting == 'existing') {
  name: connectedResourceName
}

// Conditionally creates a new Azure AI Search resource
resource newAppInsights 'Microsoft.Insights/components@2020-02-02' = if (newOrExisting == 'new') {
  name: connectedResourceName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

// Creates the Azure Foundry connection to your Azure App Insights resource
resource appinsightsconnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: '${aiFoundryName}-appinsights'
  parent: aiFoundry
  dependsOn: [
    rbacAssignment
    connection
  ]
  properties: {
    category: 'AppInsights'
    target: ((newOrExisting == 'new') ? newAppInsights.id : existingAppInsights.id)
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: ((newOrExisting == 'new') ? newAppInsights.properties.ConnectionString : existingAppInsights.properties.ConnectionString)
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: ((newOrExisting == 'new') ? newAppInsights.id : existingAppInsights.id)
    }
  }
}
