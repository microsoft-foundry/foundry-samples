targetScope = 'subscription'

@description('Name of the resource group containing the Microsoft Foundry account.')
param resourceGroupName string

@description('Name of the existing Microsoft Foundry account.')
param accountName string

@description('Name of the existing Microsoft Foundry project.')
param projectName string

module connections 'connections.bicep' = {
  name: 'personal-m365-productivity-connections'
  scope: resourceGroup(resourceGroupName)
  params: {
    accountName: accountName
    projectName: projectName
  }
}
