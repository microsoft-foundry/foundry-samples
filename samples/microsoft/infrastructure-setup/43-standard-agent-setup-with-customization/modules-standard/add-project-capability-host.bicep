param cosmosDBConnection string
param azureStorageConnection string
param aiSearchConnection string
param projectName string
param accountName string
param projectCapHost string
param accountCapHost string
param aoaiPassedIn bool
param existingAoaiConnection string

var threadConnections = ['${cosmosDBConnection}']
var storageConnections = ['${azureStorageConnection}']
var vectorStoreConnections = ['${aiSearchConnection}']

var aoaiConnection = ['${existingAoaiConnection}']


resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
   name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  name: projectName
  parent: account
}

resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
   name: accountCapHost
   parent: account
   properties: {
     capabilityHostKind: 'Agents'

   }
}


resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = if (!aoaiPassedIn) {
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

resource projectCapabilityHostAoai 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = if (aoaiPassedIn) {
  name: projectCapHost
  parent: project
  properties: {
    capabilityHostKind: 'Agents'
    vectorStoreConnections: vectorStoreConnections
    storageConnections: storageConnections
    threadStorageConnections: threadConnections

    //Set Aoai connection if it is passed in
    aiServicesConnections: aoaiConnection
  }
  dependsOn: [
    accountCapabilityHost
  ]
}
