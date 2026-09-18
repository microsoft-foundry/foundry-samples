param accountName string
param location string
param modelName string
param modelFormat string
param modelVersion string
param modelSkuName string
param modelCapacity int
param agentSubnetId string
param networkInjection string = 'true'

// True BYO Foundry account.
// When existingAccountResourceId is set, reference the existing AI Foundry
// (Cognitive Services AIServices kind) account instead of creating a new one
// with a deterministic suffix (which orphans on re-runs and collides on conflict).
@description('Optional. Full ARM resource ID of an existing AI Foundry (CognitiveServices/accounts kind=AIServices) account to reuse. When set, the template will NOT create a new account.')
param existingAccountResourceId string = ''

@description('Optional. When true, skip the model deployment. Recommended when reusing an existing account that already has the required model deployments.')
param skipModelDeployment bool = false

var useExistingAccount = !empty(existingAccountResourceId)
var existingParts = split(existingAccountResourceId, '/')
var existingAccountSub = useExistingAccount ? existingParts[2] : subscription().subscriptionId
var existingAccountRg  = useExistingAccount ? existingParts[4] : resourceGroup().name
var existingAccountName = useExistingAccount ? last(existingParts) : accountName

#disable-next-line BCP036
resource account 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' = if (!useExistingAccount) {
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    networkAcls: {
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
      bypass:'AzureServices'
    }
    publicNetworkAccess: 'Disabled'
    networkInjections:((networkInjection == 'true') ? [
      {
        scenario: 'agent'
        subnetArmId: agentSubnetId
        useMicrosoftManagedNetwork: false
      }
      ] : null )
    disableLocalAuth: false
  }
}

// Reference to existing account (cross-RG / cross-sub aware)
resource existingAccount 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' existing = {
  name: existingAccountName
  scope: resourceGroup(existingAccountSub, existingAccountRg)
}

#disable-next-line BCP081
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-15-preview' = if (!useExistingAccount && !skipModelDeployment) {
  parent: account
  name: modelName
  sku : {
    capacity: modelCapacity
    name: modelSkuName
  }
  properties: {
    model:{
      name: modelName
      format: modelFormat
      version: modelVersion
    }
  }
}

// Outputs use ARM short-circuit ternary so only the chosen branch is evaluated.
output accountName string = useExistingAccount ? existingAccount.name : account.name
output accountID string = useExistingAccount ? existingAccount.id : account.id
output accountTarget string = useExistingAccount ? existingAccount.properties.endpoint : account.properties.endpoint
output accountPrincipalId string = useExistingAccount ? existingAccount.identity.principalId : account.identity.principalId
