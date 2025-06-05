/*
Virtual Network Module
This module deploys the core network infrastructure with security controls:

1. Address Space:
   - VNet CIDR: 172.16.0.0/16 OR 192.168.0.0/16
   - Agents Subnet: 172.16.0.0/24 OR 192.168.0.0/24
   - Private Endpoint Subnet: 172.16.101.0/24 OR 192.168.1.0/24

2. Security Features:
   - Network isolation
   - Subnet delegation
   - Private endpoint subnet 
*/

@description('Azure region for the deployment')
param location string

@description('The name of the virtual network')
param vnetName string = 'agents-vnet-test'

@description('The name of Agents Subnet')
param agentSubnetName string = 'agent-subnet'

@description('The name of Hub subnet')
param peSubnetName string = 'pe-subnet'


resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.1.48.0/20'
      ]
    }
    subnets: [
      {
        name: agentSubnetName
        properties: {
          addressPrefix: '10.1.48.0/24'
          delegations: [
            {
              name: 'Microsoft.app/environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: peSubnetName
        properties: {
          addressPrefix: '10.1.49.0/24'
        }
      }
    ]
  }
}
// Output variables
output peSubnetName string = peSubnetName
output agentSubnetName string = agentSubnetName
output agentSubnetId string = '${virtualNetwork.id}/subnets/${agentSubnetName}'
output virtualNetworkName string = virtualNetwork.name
