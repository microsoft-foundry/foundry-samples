/*
  AI Foundry using Customer Managed Keys (CMK) for data encryption
  
  Description: 
  - Create an Azure AI Foundry account 
  - Create a project
  - Create a model deployment
  
  Important: Agent APIs do not support customer-managed key encryption in basic setup. 
  To use customer-managed key encryption with Agents, you must bring your own storage
  resources using 'standard' agent setup. Also, see example 31.
*/
@description('That name is the name of our application. It has to be unique. Type a name followed by your resource group name. (<name>-<resourceGroupName>)')
param aiFoundryName string = '<yourfoundry>'

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Name of the Azure Key Vault target')
param keyVaultName string = '<your-key-vault>'

@description('Name of the Azure Key Vault key')
param keyName string = '<your-key>'

@description('Version of the Azure Key Vault key')
param keyVersion string = '<your-key-version>'

var keyVaultUri = 'https://${keyVaultName}.vault.azure.net/'

/*
  An AI Foundry resources is a variant of a CognitiveServices/account resource type
*/ 
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiFoundryName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    // Networking
    publicNetworkAccess: 'Enabled'

    // Set to use with AI Foundry
    allowProjectManagement: true

    // Enable EntraID and disable key-based auth. Note that some AI Foundry features only support EntraID.
    customSubDomainName: aiFoundryName
    disableLocalAuth: false
  }
}

// Projects are folders to organize your work in AI Foundry such as Agents, Evaluations, Files
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: 'first-project'
  identity: {
    type: 'SystemAssigned'
  }
  parent: account
  location: location
  properties: {
    displayName: 'project'
    description: 'My first project'
  }
}

// Set up customer-managed key encryption once the system-assigned managed identities are created
module encryptionUpdate 'updateEncryption.bicep' = {
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
}

output accountId string = account.id
output accountName string = account.name
