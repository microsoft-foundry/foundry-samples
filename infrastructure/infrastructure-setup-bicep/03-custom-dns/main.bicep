param aiFoundryName string = 'foundry-name'
param customDNSName string = 'foundry-alt-custom-dns'
param aiProjectName string = '${aiFoundryName}-proj'
param location string = 'eastus2'

/*
  An AI Foundry resources is a variant of a CognitiveServices/account resource type
*/ 
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiFoundryName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  properties: {
    // required to work in AI Foundry
    allowProjectManagement: true

    // Defines developer API endpoint subdomain
    customSubDomainName: customDNSName

    disableLocalAuth: false
  }
}

/*
  Developer APIs are exposed via a project, which groups in- and outputs that relate to one use case, including files.
  Its advisable to create one project right away, so development teams can directly get started.
  Projects may be granted individual RBAC permissions and identities on top of what account provides.
*/ 
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: aiProjectName
  parent: aiFoundry
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

/*
  Optionally deploy a model to use in playground, agents and other tools.
*/
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01'= {
  parent: aiFoundry
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

/*
  Optionally deploy a model to use in playground, agents and other tools.
*/
// resource modelDeployment2 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01'= {
//   parent: aiFoundry
//   name: 'FLUX.1-Kontext-pro'
//   sku : {
//     capacity: 1
//     name: 'GlobalStandard'
//   }
//   properties: {
//     model: {
//       name: 'FLUX.1-Kontext-pro'
//       format: 'Black Forest Labs'
//       version: '1'
//     }
//   }
// }
