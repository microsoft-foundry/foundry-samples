targetScope = 'subscription'

@description('Name of the resource group created by the Microsoft Foundry layer.')
param resourceGroupName string

@description('Name of the Microsoft Foundry account.')
param accountName string

@description('Name of the Microsoft Foundry project.')
param projectName string

@description('Name of the azd environment.')
param environmentName string

@description('Primary location for Microsoft Foundry and Azure SQL.')
param location string

@description('Connector Namespace preview location.')
param connectorLocation string = 'westcentralus'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: resourceGroupName
}

module resources './resources.bicep' = {
  name: 'adventureworks-sql-connector'
  scope: resourceGroup
  params: {
    accountName: accountName
    projectName: projectName
    environmentName: environmentName
    location: location
    connectorLocation: connectorLocation
    deployerPrincipalId: deployer().objectId
    deployerLoginName: deployer().userPrincipalName
    tags: {
      'azd-env-name': environmentName
    }
  }
}

output SQL_SERVER_NAME string = resources.outputs.sqlServerName
output SQL_SERVER_FQDN string = resources.outputs.sqlServerFqdn
output SQL_DATABASE_NAME string = resources.outputs.sqlDatabaseName
output CONNECTOR_NAMESPACE_NAME string = resources.outputs.connectorNamespaceName
output CONNECTOR_NAMESPACE_PRINCIPAL_ID string = resources.outputs.connectorNamespacePrincipalId
output FOUNDRY_PROJECT_PRINCIPAL_ID string = resources.outputs.foundryProjectPrincipalId
output SQL_CONNECTOR_CONNECTION_ID string = resources.outputs.sqlConnectionId
output SQL_MCP_SERVER_URL string = resources.outputs.mcpEndpointUrl
