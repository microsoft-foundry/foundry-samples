param accountName string
param location string
param modelName string
param modelFormat string
param modelVersion string
param modelSkuName string
param modelCapacity int

#disable-next-line BCP036

//AIO Mode managed virtual network 
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
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
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Disabled'
    networkInjections: [
      {
        scenario: ''
        subnetArmId: ''
        useMicrosoftManagedNetwork: true
      }
    ]
    disableLocalAuth: false
  }
}

//AOAO omde managed virtual network
/*resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
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
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Disabled'
    networkInjections: [
      {
        scenario: ''
        subnetArmId: ''
        useMicrosoftManagedNetwork: true
      }
    ]
    disableLocalAuth: false
    managed_network: {
      isolation_mode: 'allow_only_approved_outbound'
      //network_id: 
      outbound_rules: {
          name: 'added-perule'
          type: 'fqdn'
          destination: 'azure.com'
          category: 'user_defined'
      }
      managedNetworkKind: 'V2'
      enableNetworkMonitor: true
      //enableFirewallLog: true
    }
  }
} */

#disable-next-line BCP081
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview'=  {
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

output accountName string = account.name
output accountID string = account.id
output accountTarget string = account.properties.endpoint
output accountPrincipalId string = account.identity.principalId
