/*
Virtual Network Module
This module works with existing virtual networks and required subnets.

1. Flexibility:
   - Works with any existing VNet address space
   - Can use existing subnets or create new ones
   - Cross-resource group support

2. Security Features:
   - Network isolation
   - Subnet delegation for containerized workloads
   - Private endpoint subnet for secure connectivity
*/


@description('The name of the existing virtual network')
param vnetName string

@description('Subscription ID of virtual network (if different from current subscription)')
param vnetSubscriptionId string = subscription().subscriptionId

@description('Resource Group name of the existing VNet (if different from current resource group)')
param vnetResourceGroupName string = resourceGroup().name

@description('The name of Agents Subnet')
param agentSubnetName string = 'agent-subnet'

@description('The name of Private Endpoint subnet')
param peSubnetName string = 'pe-subnet'

@description('Address prefix for the agent subnet (only needed if creating new subnet)')
param agentSubnetPrefix string = ''

@description('Address prefix for the private endpoint subnet (only needed if creating new subnet)')
param peSubnetPrefix string = ''

// Reference the existing virtual network
resource existingVNet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: vnetName
  scope: resourceGroup(vnetResourceGroupName)
}

// Get the address space (array of CIDR strings)
var vnetAddressSpace = existingVNet.properties.addressSpace.addressPrefixes[0]

var agentSubnetSpaces = empty(agentSubnetPrefix) ? cidrSubnet(vnetAddressSpace, 24, 0) : agentSubnetPrefix
var peSubnetSpaces = empty(peSubnetPrefix) ? cidrSubnet(vnetAddressSpace, 24, 1) : peSubnetPrefix

// Check if subnets exist by filtering the existing VNet's subnets
var agentSubnetExists = contains(map(existingVNet.properties.subnets, subnet => subnet.name), agentSubnetName)
var peSubnetExists = contains(map(existingVNet.properties.subnets, subnet => subnet.name), peSubnetName)

// Reference existing agent subnet if it exists
resource existingAgentSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = if (agentSubnetExists) {
  name: agentSubnetName
  parent: existingVNet
}

// Reference existing PE subnet if it exists
resource existingPeSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = if (peSubnetExists) {
  name: peSubnetName
  parent: existingVNet
}

// Create the agent subnet only if it doesn't exist
module agentSubnet 'subnet.bicep' = if (!agentSubnetExists) {
  name: 'agent-subnet-${uniqueString(deployment().name, agentSubnetName)}'
  scope: resourceGroup(vnetResourceGroupName)
  params: {
    vnetName: vnetName
    subnetName: agentSubnetName
    addressPrefix: agentSubnetSpaces
    delegations: [
      {
        name: 'Microsoft.App/environments'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

// Create the private endpoint subnet only if it doesn't exist
module peSubnet 'subnet.bicep' = if (!peSubnetExists) {
  name: 'pe-subnet-${uniqueString(deployment().name, peSubnetName)}'
  scope: resourceGroup(vnetResourceGroupName)
  params: {
    vnetName: vnetName
    subnetName: peSubnetName
    addressPrefix: peSubnetSpaces
    delegations: []
  }
}

// Output variables
output peSubnetName string = peSubnetName
output agentSubnetName string = agentSubnetName
output agentSubnetId string = agentSubnetExists ? existingAgentSubnet.id : agentSubnet.outputs.subnetId
output peSubnetId string = peSubnetExists ? existingPeSubnet.id : peSubnet.outputs.subnetId
output virtualNetworkName string = existingVNet.name
output virtualNetworkId string = existingVNet.id
output virtualNetworkResourceGroup string = vnetResourceGroupName
output virtualNetworkSubscriptionId string = vnetSubscriptionId
