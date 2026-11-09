param location string
param config object

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: config.vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [config.addressPrefix]
    }
    subnets: [
      {
        name: config.agentSubnetName
        properties: {
          addressPrefix: config.agentSubnetPrefix
          delegations: [
            {
              name: 'agent-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: config.privateEndpointSubnetName
        properties: {
          addressPrefix: config.privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output agentSubnetResourceId string = '${network.id}/subnets/${config.agentSubnetName}'
output privateEndpointSubnetResourceId string = '${network.id}/subnets/${config.privateEndpointSubnetName}'
