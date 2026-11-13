// Creates the given policy assignments at resource group scope.
// main.bicep calls this when resourceGroupName is set; Bicep needs a module to
// deploy to a scope other than the calling file's targetScope.

targetScope = 'resourceGroup'

@description('Assignments to create: [{ name, properties }], built by main.bicep.')
param assignments array

resource policyAssignments 'Microsoft.Authorization/policyAssignments@2024-04-01' = [
  for a in assignments: {
    name: a.name
    properties: a.properties
  }
]
