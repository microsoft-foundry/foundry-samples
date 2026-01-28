using './main.bicep'

param location = 'westus'
param aiServices = 'foundry'
param modelName = 'gpt-4.1'
param modelFormat = 'OpenAI'
param modelVersion = '2025-04-14'
param modelSkuName = 'GlobalStandard'
param modelCapacity = 30
param firstProjectName = 'project'
param projectDescription = 'A project for the AI Foundry account with network secured deployed Agent'
param displayName = 'project'
param peSubnetName = 'pe-subnet'

// Resource IDs for existing resources
// If you provide these, the deployment will use the existing resources instead of creating new ones
param existingVnetResourceId = ''
param vnetName = 'agent-vnet-test'
param agentSubnetName = 'agent-subnet'
param aiSearchResourceId = ''
param azureStorageAccountResourceId = ''
param azureCosmosDBAccountResourceId = ''

// Subscription ID where DNS zones are located (leave empty to use deployment subscription)
// ⚠️ If set to a different subscription, ALL zones below MUST have resource groups specified
param dnsZonesSubscriptionId = ''

// DNS zone map: provide resource group name to use existing zone, or leave empty to create new
// Note: Empty values only allowed when dnsZonesSubscriptionId is empty or matches current subscription
param existingDnsZones = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''               
  'privatelink.search.windows.net': ''           
  'privatelink.blob.core.windows.net': ''                            
  'privatelink.documents.azure.com': ''                       
}

//DNSZones names for validating if they exist
param dnsZoneNames = [
  'privatelink.services.ai.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.search.windows.net'
  'privatelink.blob.core.windows.net'
  'privatelink.documents.azure.com'
]


// Network configuration (behavior depends on `existingVnetResourceId`)
//
// - NEW VNet (existingVnetResourceId is empty):
//     The values below are used to CREATE the VNet and the two subnets.
//     Provide explicit, non-overlapping CIDR ranges when creating a new VNet.
//
// - EXISTING VNet (existingVnetResourceId is provided):
//     The module will reference the existing VNet. Subnet handling depends on the
//     values you provide:
//       * If `agentSubnetPrefix` or `peSubnetPrefix` are empty, the module may
//         auto-derive subnet CIDRs from the existing VNet's address space
//         (using cidrSubnet). This can produce /24 (or configured) subnets
//         starting at index 0, 1, etc.
//       * If you provide explicit subnet prefixes, the module will attempt to
//         create or update subnets with those prefixes in the existing VNet.
//
// Important operational notes and risks (when existingVnetResourceId is provided):
// - Avoid CIDR overlaps with any existing subnets in the target VNet. Overlap
//   leads to `NetcfgSubnetRangesOverlap` and failed deployments.
// - For highest safety when using an existing VNet, supply the existing `agentSubnetPrefix` and `peSubnetPrefix`. 
param vnetAddressPrefix = ''
param agentSubnetPrefix = ''
param peSubnetPrefix = ''

