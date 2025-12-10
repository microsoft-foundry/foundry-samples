@description('Name of the virtual network')
param vnetName string

@description('Name of the subnet')
param subnetName string

@description('Address prefix for the subnet')
param addressPrefix string

resource subnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  name: '${vnetName}/${subnetName}'
  properties: {
    addressPrefix: addressPrefix
  }
}

output subnetId string = subnet.id
output subnetName string = subnetName
