@description('Name of the Microsoft Foundry account.')
param accountName string

@description('Name of the Microsoft Foundry project.')
param projectName string

@description('Name of the azd environment.')
param environmentName string

@description('Primary location for Azure SQL.')
param location string

@description('Connector Namespace preview location.')
param connectorLocation string

@description('Object ID of the deployer user.')
param deployerPrincipalId string

@description('Microsoft Entra login name of the deployer user.')
param deployerLoginName string

param tags object = {}

var resourceToken = take(toLower(uniqueString(subscription().id, environmentName, resourceGroup().id)), 8)
var sqlServerName = 'sql-${resourceToken}'
var sqlDatabaseName = 'AdventureWorksLT'
var connectorNamespaceName = 'cn-sql-${resourceToken}'
var sqlConnectionName = 'sql-adventureworks'
var mcpServerConfigName = 'sql-adventureworks-readonly'
var fixedSqlTargetParameters = [
  {
    name: 'server'
    value: sqlServer.properties.fullyQualifiedDomainName
  }
  {
    name: 'database'
    value: sqlDatabase.name
  }
]

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: foundryAccount
  name: projectName
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: deployerLoginName
      sid: deployerPrincipalId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: true
    }
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 2147483648
    sampleName: 'AdventureWorksLT'
  }
}

#disable-next-line BCP081
resource connectorNamespace 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: connectorNamespaceName
  location: connectorLocation
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

#disable-next-line BCP081
resource sqlConnection 'Microsoft.Web/connectorGateways/connections@2026-05-01-preview' = {
  parent: connectorNamespace
  name: sqlConnectionName
  properties: {
    connectorName: 'sql'
    displayName: 'AdventureWorks SQL Connection'
    parameterValueSet: {
      name: 'oauthMI'
      values: {}
    }
  }
}

#disable-next-line BCP081
resource projectConnectionAccess 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: sqlConnection
  name: 'foundry-project-msi'
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: foundryProject.identity.principalId
        tenantId: tenant().tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource deployerConnectionAccess 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: sqlConnection
  name: deployerPrincipalId
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: deployerPrincipalId
        tenantId: tenant().tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource namespaceConnectionAccess 'Microsoft.Web/connectorGateways/connections/accessPolicies@2026-05-01-preview' = {
  parent: sqlConnection
  name: 'connector-namespace-msi'
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        objectId: connectorNamespace.identity.principalId
        tenantId: tenant().tenantId
      }
    }
  }
}

#disable-next-line BCP081
resource sqlMcpServer 'Microsoft.Web/connectorGateways/mcpserverconfigs@2026-05-01-preview' = {
  parent: connectorNamespace
  name: mcpServerConfigName
  properties: {
    state: 'Enabled'
    description: 'Read-only tools for the AdventureWorksLT Azure SQL database.'
    connectors: [
      {
        name: 'sql'
        connectionName: sqlConnection.name
        displayName: 'AdventureWorks SQL'
        description: 'Read-only access to the AdventureWorksLT sample database.'
        operations: [
          {
            name: 'GetTables_V2'
            displayName: 'List database tables'
            description: 'Lists tables in the AdventureWorksLT database.'
            userParameters: fixedSqlTargetParameters
            agentParameters: []
          }
          {
            name: 'GetItems_V2'
            displayName: 'Read table rows'
            description: 'Reads rows from an AdventureWorksLT table with optional OData filtering.'
            userParameters: fixedSqlTargetParameters
            agentParameters: [
              {
                name: 'table'
                schema: {
                  type: 'string'
                  description: 'SQL table name, including schema when returned by the list-tables tool.'
                  required: true
                }
              }
              {
                name: '$filter'
                schema: {
                  type: 'string'
                  description: 'Optional OData filter expression.'
                }
              }
              {
                name: '$orderby'
                schema: {
                  type: 'string'
                  description: 'Optional OData order-by expression.'
                }
              }
              {
                name: '$select'
                schema: {
                  type: 'string'
                  description: 'Optional comma-separated columns to return.'
                }
              }
              {
                name: '$top'
                schema: {
                  type: 'integer'
                  format: 'int32'
                  description: 'Maximum number of rows to return.'
                }
              }
            ]
          }
          {
            name: 'GetItem_V2'
            displayName: 'Read one table row'
            description: 'Reads one row from an AdventureWorksLT table by identifier.'
            userParameters: fixedSqlTargetParameters
            agentParameters: [
              {
                name: 'table'
                schema: {
                  type: 'string'
                  description: 'SQL table name, including schema.'
                  required: true
                }
              }
              {
                name: 'id'
                schema: {
                  type: 'string'
                  description: 'Unique row identifier.'
                  required: true
                }
              }
            ]
          }
          {
            name: 'ExecutePassThroughNativeQuery_V2'
            displayName: 'Run a read-only SQL query'
            description: 'Runs a read-only SELECT query against AdventureWorksLT.'
            userParameters: fixedSqlTargetParameters
            agentParameters: [
              {
                name: 'query/query'
                schema: {
                  type: 'string'
                  description: 'A bounded read-only SELECT query. Data modification statements are not permitted.'
                  required: true
                }
              }
            ]
          }
        ]
      }
    ]
    policies: []
    settings: {
      textOnlyContent: true
    }
  }
}

output sqlServerName string = sqlServer.name
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDatabase.name
output connectorNamespaceName string = connectorNamespace.name
output connectorNamespacePrincipalId string = connectorNamespace.identity.principalId
output foundryProjectPrincipalId string = foundryProject.identity.principalId
output sqlConnectionId string = sqlConnection.id
output mcpEndpointUrl string = sqlMcpServer.properties.mcpEndpointUrl
