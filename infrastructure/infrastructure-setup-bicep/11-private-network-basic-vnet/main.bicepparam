using './main.bicep'

param location = 'eastus'
param aiServices = 'foundry'
param modelName = 'gpt-4.1'
param modelFormat = 'OpenAI'
param modelVersion = '2025-04-14'
param modelSkuName = 'GlobalStandard'
param modelCapacity = 30
param firstProjectName = 'project'
param projectDescription = 'A project for the AI Foundry account with network secured basic Agent'
param displayName = 'project'
param peSubnetName = 'pe-subnet'

// Virtual Network parameters
// If you provide an existing VNet resource ID, the deployment will use it instead of creating a new one
param existingVnetResourceId = ''
param vnetName = 'agent-vnet-test'
param agentSubnetName = 'agent-subnet'

// DNS zone parameters
// Leave empty to create new DNS zones, or provide resource group names to use existing ones
param dnsZonesSubscriptionId = ''
param existingDnsZones = {
  'privatelink.services.ai.azure.com': ''
  'privatelink.openai.azure.com': ''
  'privatelink.cognitiveservices.azure.com': ''
  'privatelink.azurecr.io': ''
}
