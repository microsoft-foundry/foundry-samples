param cosmosDBConnection string 
param azureStorageConnection string 
param aiSearchConnection string
param projectName string
param accountName string
param projectCapHost string
param accountCapHost string

var threadConnections = ['${cosmosDBConnection}']
var storageConnections = ['${azureStorageConnection}']
var vectorStoreConnections = ['${aiSearchConnection}']

#disable-next-line BCP081
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
   name: accountName
}
#disable-next-line BCP081
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  name: projectName
  parent: account
}

#disable-next-line BCP081
 resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
   name: accountCapHost
   parent: account
   properties: {
     capabilityHostKind: 'Agents'
   }
}

#disable-next-line BCP081
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: projectCapHost
  parent: project
  properties: {
    capabilityHostKind: 'Agents'
    vectorStoreConnections: vectorStoreConnections
    storageConnections: storageConnections
    threadStorageConnections: threadConnections
  }
  dependsOn: [
    accountCapabilityHost
  ]
}
