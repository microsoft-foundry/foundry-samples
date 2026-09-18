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

// Non-destructive subnet handling.
// When the caller already has correctly-configured subnets (delegations, NSGs,
// route tables, privateEndpointNetworkPolicies), the original template would
// PUT a slim subnet body (only addressPrefix + delegations) and ARM would
// silently RESET privateEndpointNetworkPolicies (and clobber NSG/RT references)
// to defaults. In tenants that enforce a policy on those properties, this
// fails with RequestDisallowedByPolicy.
// When reuseExistingSubnets=true we skip the subnet PUT entirely and just
// reference the existing subnet IDs in the outputs.
@description('When true, do NOT modify the existing subnets, reference them as-is. Recommended when the caller manages subnet config (NSG/RT/PE policies) outside this template.')
param reuseExistingSubnets bool = false

// Get the address space (array of CIDR strings)
var vnetAddressSpace = existingVNet.properties.addressSpace.addressPrefixes[0]

var agentSubnetSpaces = empty(agentSubnetPrefix) ? cidrSubnet(vnetAddressSpace, 24, 0) : agentSubnetPrefix
var peSubnetSpaces = empty(peSubnetPrefix) ? cidrSubnet(vnetAddressSpace, 24, 1) : peSubnetPrefix

// Reference the existing virtual network
resource existingVNet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: vnetName
  scope: resourceGroup(vnetResourceGroupName)
}

// Create the agent subnet if requested
module agentSubnet 'subnet.bicep' = if (!reuseExistingSubnets) {
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

// Create the private endpoint subnet if requested
module peSubnet 'subnet.bicep' = if (!reuseExistingSubnets) {
  name: 'pe-subnet-${uniqueString(deployment().name, peSubnetName)}'
  scope: resourceGroup(vnetResourceGroupName)
  params: {
    vnetName: vnetName
    subnetName: peSubnetName
    addressPrefix: peSubnetSpaces
    delegations: []
  }
  dependsOn: [
    agentSubnet
  ]
}

// Output variables
output peSubnetName string = peSubnetName
output agentSubnetName string = agentSubnetName
output agentSubnetId string = '${existingVNet.id}/subnets/${agentSubnetName}'
output peSubnetId string = '${existingVNet.id}/subnets/${peSubnetName}'
output virtualNetworkName string = existingVNet.name
output virtualNetworkId string = existingVNet.id
output virtualNetworkResourceGroup string = vnetResourceGroupName
output virtualNetworkSubscriptionId string = vnetSubscriptionId
