/*
  AI Foundry using Customer Managed Keys (CMK) for data encryption
  
  Description: 
  - Create an Azure AI Foundry account 
  - Create a project
  - Create a model deployment
  
  Important: Agent APIs do not support customer-managed key encryption in basic setup. 
  To use customer-managed key encryption with Agents, you must bring your own storage
  resources using 'standard' agent setup. Also, see example 31.

  Note: due to role assignment delay, initial template run by may fail if the managed identity has no access to your key vault yet. Retry running the template.
*/
param aiFoundryName string = 'foundry-cmk'

param aiProjectName string = '${aiFoundryName}-proj'

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Name of the Azure Key Vault target')
param keyVaultName string = 'foundry-int-cmk-akv'

@description('Name of the Azure Key Vault key')
param keyName string = 'key'

@description('Version of the Azure Key Vault key')
param keyVersion string = '01389af5911f49878d68c29136648b8d'

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
  name: aiProjectName
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

/*
  Optionally deploy a model to use in playground, agents and other tools.
*/
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01'= {
  parent: account
  name: 'gpt-4.1-mini'
  sku : {
    capacity: 1
    name: 'GlobalStandard'
  }
  properties: {
    model:{
      name: 'gpt-4.1-mini'
      format: 'OpenAI'
      version: '2025-04-14'
    }
  }
}

output accountId string = account.id
output accountName string = account.name
