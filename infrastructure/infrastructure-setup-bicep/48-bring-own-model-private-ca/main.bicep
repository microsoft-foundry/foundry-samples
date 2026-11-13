// ============================================================================
// 48-bring-own-model-private-ca  (Bicep port of the Terraform sample)
//
// Reproduce, then fix, a TLS "certificate not trusted" error on the Foundry
// connected-model inferencing path when the model is fronted by a gateway
// (nginx) that presents a private-CA certificate on an internal-only custom
// domain. The single-tenant data proxy — provisioned inside the VNet by the
// project capability host — is the TLS chokepoint under test.
//
// Two-phase test, driven by the enablePrivateCaTrust parameter:
//   * false (REPRO)  = root CA is NOT on the account. Inference
//                      through the connected model fails at the data proxy
//                      with certificate-not-trusted.
//   * true  (VERIFY) = root CA public PEM is registered (as a Key Vault
//                      SECRET) in account.properties.trustedCertificateSources.
//                      After the account update succeeds, trust propagates
//                      automatically to project capability hosts.
//
// Deploy at resource-group scope:
//   az group create -n rg-byomca -l eastus2
//   az deployment group create -g rg-byomca -f main.bicep -p main.bicepparam
// ============================================================================

targetScope = 'resourceGroup'

// ----------------------------------------------------------------------------
// Parameters
// ----------------------------------------------------------------------------
@description('Azure region for all resources.')
@allowed([
  'australiaeast'
  'brazilsouth'
  'canadacentral'
  'canadaeast'
  'centralindia'
  'centralus'
  'eastasia'
  'eastus'
  'eastus2'
  'francecentral'
  'germanywestcentral'
  'italynorth'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'northeurope'
  'norwayeast'
  'qatarcentral'
  'southafricanorth'
  'southcentralus'
  'southindia'
  'southeastasia'
  'spaincentral'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westeurope'
  'westus'
  'westus3'
  'usgovarizona'
  'usgovvirginia'
])
param location string = any(resourceGroup().location)

@description('Region for the Cosmos DB account only. Defaults to location; override (e.g. eastus2) when the main region lacks Cosmos capacity. The Cosmos private endpoint still lands in the spoke VNet in location.')
param cosmosLocation string = location

@description('Region for the Azure AI Search service only. Defaults to location; override when the main region lacks Search capacity. The Search private endpoint still lands in the spoke VNet in location.')
param searchLocation string = location

@description('Short prefix for resource names. Kept short because Key Vault and Foundry account names have length limits.')
@minLength(1)
@maxLength(11)
param namePrefix string = 'byomca'

@description('OpenAI model deployed on the Foundry model account and exposed through the gateway.')
param foundryModelName string = 'gpt-4.1'

@description('Version of the Foundry model deployment.')
param foundryModelVersion string = '2025-04-14'

@description('Capacity (thousands of tokens per minute) for the Foundry model deployment.')
param foundryModelCapacity int = 40

@description('Address space for the spoke VNet.')
param vnetAddressSpace string = '172.24.0.0/16'

@description('Delegated Standard-Agent subnet (Microsoft.App/environments). Injecting the account here provisions the agent runtime + single-tenant data proxy.')
param agentSubnetPrefix string = '172.24.1.0/24'

@description('Private-endpoint subnet (Foundry account, Storage, Cosmos, Search).')
param peSubnetPrefix string = '172.24.2.0/24'

@description('Internal-only private DNS zone for the gateway custom domain (a BYO-gateway VAN-URL analog). The self-signed cert SAN must match <customDomainHost>.<customDomainZone>.')
param customDomainZone string = 'byomca.internal'

@description('Host label of the gateway custom domain, prepended to customDomainZone.')
param customDomainHost string = 'gateway'

@description('CIDR for the delegated subnet that hosts the nginx gateway container (Azure Container Instances).')
param aciSubnetPrefix string = '172.24.3.0/24'

@description('Base64-encoded PEM of the self-signed gateway certificate (public cert). Emitted by bootstrap-cert; served by nginx on the TLS handshake the data proxy validates. Supplied by deploy.ps1.')
@secure()
param gatewayCertPemB64 string = ''

@description('Base64-encoded PEM of the self-signed gateway private key. Emitted by bootstrap-cert; used by nginx to serve the cert. Supplied by deploy.ps1.')
@secure()
param gatewayKeyPemB64 string = ''

@description('Inference API version the Foundry ApiManagement connection sends to the gateway.')
param inferenceApiVersion string = '2024-10-21'

@description('Name of the pre-created Key Vault that holds the root CA public-cert PEM secret (created by bootstrap-cert.ps1/.sh before this deployment).')
param keyVaultName string

@description('Pinned version of the root CA public-cert PEM Key Vault SECRET. Only needed for the VERIFY phase (enablePrivateCaTrust=true); leave empty for REPRO. Emitted by the bootstrap script.')
param gatewayCaSecretVersion string = ''

@description('Name of the root CA public-cert PEM Key Vault SECRET (the trust anchor referenced by account.trustedCertificateSources). Must match the -SecretName used by the bootstrap script; deploy.ps1 forwards it automatically.')
param gatewayCaSecretName string = 'trustedca-root-pem'

@description('''Two-phase test switch.
false (default) = REPRO: root CA NOT registered on the account; inference is expected to FAIL at the data proxy with certificate-not-trusted.
true = VERIFY: root CA (public PEM) registered in account.trustedCertificateSources; wait for the account update to succeed and trust to propagate, then inference is expected to SUCCEED.''')
param enablePrivateCaTrust bool = false

// ----------------------------------------------------------------------------
// Naming / computed values
// ----------------------------------------------------------------------------
var suffix = take(uniqueString(resourceGroup().id), 5)

var foundryModelAccountName = toLower(replace('${namePrefix}models${suffix}', '-', ''))
var foundryAgentAccountName = toLower(replace('${namePrefix}agents${suffix}', '-', ''))
var gatewayAciName = '${namePrefix}-gw-${suffix}'
var lawName = 'law-${namePrefix}-${suffix}'
var appiName = 'appi-${namePrefix}-${suffix}'
var vnetName = 'vnet-${namePrefix}-${suffix}'
var sanitizedNamePrefix = toLower(replace(namePrefix, '-', ''))
var storageName = '${sanitizedNamePrefix}stg${suffix}'
var cosmosName = toLower('${namePrefix}-cosmos-${suffix}')
var searchName = toLower('${namePrefix}-search-${suffix}')

var customDomainFqdn = '${customDomainHost}.${customDomainZone}'
// gatewayCaSecretName (parameter) names the ROOT CA public-cert PEM stored as a
// Key Vault SECRET. The trusted-cert resolver reads a KV SECRET (public PEM),
// not a certificate object; referencing a certificate object fails with
// InvalidReference.
var natGatewayName = 'ng-${namePrefix}-${suffix}'
var natPublicIpName = 'pip-ng-${namePrefix}-${suffix}'

var apimApiPath = 'inference'
var tokenAudience = 'https://cognitiveservices.azure.com'

// Connected model targets the self-signed custom domain (served by the nginx
// gateway container, NOT a public Microsoft cert that would let the data proxy
// OS-trust short-circuit).
var gatewayTarget = 'https://${customDomainFqdn}/${apimApiPath}'
var modelHost = '${foundryModelAccountName}.openai.azure.com'
var foundryModelEndpoint = 'https://${modelHost}'

// Approved catalog surfaced on the connected model. metadata.models must be a
// JSON *string* for the Foundry portal picker.
var approvedCatalogModelsJson = '[{"name":"${foundryModelName}","properties":{"model":{"name":"${foundryModelName}","version":"1","format":"OpenAI"}}}]'

var gatewayConnectionMetadata = {
  audience: tokenAudience
  deploymentInPath: 'true'
  inferenceAPIVersion: inferenceApiVersion
  models: approvedCatalogModelsJson
  customHeaders: '{}'
  authConfig: '{}'
}

var commonTags = {
  scenario: 'byom-private-ca'
  sample: '48-bring-own-model-private-ca'
}

// Private DNS zones linked to the spoke VNet (index order matters, see below).
var privateDnsZoneNames = [
  'privatelink.cognitiveservices.azure.com' // 0
  'privatelink.openai.azure.com'            // 1
  'privatelink.services.ai.azure.com'       // 2
  'privatelink.blob.${environment().suffixes.storage}' // 3
  'privatelink.documents.azure.com'         // 4
  'privatelink.search.windows.net'          // 5
]

// Built-in role definition IDs.
var roleCognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var roleKeyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var roleStorageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var roleStorageBlobDataOwner = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var roleCosmosDbOperator = '230815da-be43-4aae-9cb4-875f7bd000aa'
var roleSearchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var roleSearchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var cosmosBuiltInDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

// ----------------------------------------------------------------------------
// Monitoring
// ----------------------------------------------------------------------------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: appiName
  location: location
  kind: 'web'
  tags: commonTags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
  }
}

// ----------------------------------------------------------------------------
// Explicit outbound for the gateway ACI subnet. The nginx container must reach
// the public model endpoint; a NAT gateway provides deterministic egress
// instead of relying on (retiring) default outbound access.
// ----------------------------------------------------------------------------
resource natPublicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: natPublicIpName
  location: location
  tags: commonTags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-11-01' = {
  name: natGatewayName
  location: location
  tags: commonTags
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

// ----------------------------------------------------------------------------
// Network: spoke VNet with a delegated agent subnet + a PE subnet.
// ----------------------------------------------------------------------------
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: commonTags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressSpace
      ]
    }
    subnets: [
      {
        name: 'snet-agent'
        properties: {
          addressPrefixes: [
            agentSubnetPrefix
          ]
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
      {
        name: 'snet-pe'
        properties: {
          addressPrefixes: [
            peSubnetPrefix
          ]
        }
      }
      {
        name: 'snet-aci'
        properties: {
          addressPrefixes: [
            aciSubnetPrefix
          ]
          natGateway: {
            id: natGateway.id
          }
          delegations: [
            {
              name: 'Microsoft.ContainerInstance/containerGroups'
              properties: {
                serviceName: 'Microsoft.ContainerInstance/containerGroups'
              }
            }
          ]
        }
      }
    ]
  }
}

resource agentSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-11-01' existing = {
  parent: vnet
  name: 'snet-agent'
}

resource peSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-11-01' existing = {
  parent: vnet
  name: 'snet-pe'
}

resource aciSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-11-01' existing = {
  parent: vnet
  name: 'snet-aci'
}

// ----------------------------------------------------------------------------
// Private DNS zones + VNet links.
// ----------------------------------------------------------------------------
resource privateDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for name in privateDnsZoneNames: {
  name: name
  location: 'global'
  tags: commonTags
}]

resource privateDnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (name, i) in privateDnsZoneNames: {
  parent: privateDnsZones[i]
  name: 'link-${suffix}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

// Gateway self-signed custom-domain zone (internal-only VAN-URL analog).
resource customZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: customDomainZone
  location: 'global'
  tags: commonTags
}

resource customZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: customZone
  name: 'link-${suffix}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// ----------------------------------------------------------------------------
// Key Vault (RBAC) + the self-signed cert are created OUT OF BAND by
// bootstrap-cert.ps1 / .sh before this template runs. ARM deploymentScripts
// cannot be used here because they require a helper storage account with shared
// key auth, which this subscription's policy denies. The vault is referenced as
// an existing resource; RBAC for the Foundry account MI is still granted below
// (role assignments work on an existing scope).
// ----------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// ----------------------------------------------------------------------------
// Foundry model backend (the real model behind the gateway). Public network
// access stays enabled so the nginx gateway's backend leg can reach it.
// ----------------------------------------------------------------------------
resource modelAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: foundryModelAccountName
  location: location
  kind: 'AIServices'
  tags: commonTags
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: false
    customSubDomainName: foundryModelAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: modelAccount
  name: foundryModelName
  sku: {
    name: 'GlobalStandard'
    capacity: foundryModelCapacity
  }
  properties: {
    model: {
      name: foundryModelName
      format: 'OpenAI'
      version: foundryModelVersion
    }
  }
}

// Project MI can mint backend tokens for the model account. The connected-model
// connection uses ProjectManagedIdentity auth (aud=cognitiveservices); the nginx
// gateway forwards that Authorization header straight to the model account.
resource projectCogUserOnModel 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: modelAccount
  name: guid(modelAccount.id, project.id, roleCognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCognitiveServicesUser)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ----------------------------------------------------------------------------
// nginx gateway (Azure Container Instances) serving the self-signed cert on the
// internal custom domain. This replaces APIM: a plain reverse proxy has no
// custom-domain ownership check, so an internal-only FQDN + self-signed cert
// works directly. It terminates TLS with the bootstrap cert and forwards the
// data proxy's Authorization header (ProjectManagedIdentity, aud=cognitiveservices)
// straight to the model account's /openai endpoint.
// ----------------------------------------------------------------------------
var nginxConfTemplate = '''
worker_processes 1;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log /dev/stdout;
  proxy_http_version 1.1;
  server {
    listen 443 ssl;
    server_name __FQDN__;
    ssl_certificate     /mnt/certs/server.crt;
    ssl_certificate_key /mnt/certs/server.key;
    location /__APIPATH__/ {
      proxy_pass https://__MODELHOST__/openai/;
      proxy_set_header Host __MODELHOST__;
      proxy_ssl_server_name on;
      proxy_ssl_name __MODELHOST__;
      proxy_ssl_verify on;
      proxy_ssl_verify_depth 3;
      proxy_ssl_trusted_certificate /etc/pki/tls/certs/ca-bundle.crt;
    }
    location / { return 200 'gateway-ok'; }
  }
}
'''

var nginxConf = replace(replace(replace(nginxConfTemplate, '__FQDN__', customDomainFqdn), '__APIPATH__', apimApiPath), '__MODELHOST__', modelHost)

resource gatewayAci 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: gatewayAciName
  location: location
  tags: commonTags
  properties: {
    sku: 'Standard'
    osType: 'Linux'
    restartPolicy: 'Always'
    subnetIds: [
      {
        id: aciSubnet.id
      }
    ]
    ipAddress: {
      type: 'Private'
      ports: [
        {
          protocol: 'TCP'
          port: 443
        }
      ]
    }
    volumes: [
      {
        name: 'certs'
        secret: {
          'server.crt': gatewayCertPemB64
          'server.key': gatewayKeyPemB64
        }
      }
      {
        name: 'conf'
        secret: {
          'nginx.conf': base64(nginxConf)
        }
      }
    ]
    containers: [
      {
        name: 'gateway'
        properties: {
          image: 'mcr.microsoft.com/cbl-mariner/base/nginx:1.22'
          command: [
            'nginx'
            '-c'
            '/mnt/conf/nginx.conf'
            '-g'
            'daemon off;'
          ]
          ports: [
            {
              protocol: 'TCP'
              port: 443
            }
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 1
            }
          }
          volumeMounts: [
            {
              name: 'certs'
              mountPath: '/mnt/certs'
              readOnly: true
            }
            {
              name: 'conf'
              mountPath: '/mnt/conf'
              readOnly: true
            }
          ]
        }
      }
    ]
  }
}

// Gateway custom-domain A record -> nginx container's private IP. The cert nginx
// serves on this hostname is the self-signed cert whose SAN == customDomainFqdn.
resource gatewayARecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: customZone
  name: customDomainHost
  properties: {
    ttl: 60
    aRecords: [
      {
        ipv4Address: gatewayAci.properties.ipAddress.ip
      }
    ]
  }
}

// ----------------------------------------------------------------------------
// VNet-injected Foundry agent account (hosts the project + single-tenant data
// proxy). trustedCertificateSources is added ONLY in the VERIFY phase.
// ----------------------------------------------------------------------------
var agentAccountBaseProperties = {
  allowProjectManagement: true
  customSubDomainName: foundryAgentAccountName
  publicNetworkAccess: 'Enabled'
  disableLocalAuth: true
  networkAcls: {
    defaultAction: 'Allow'
    virtualNetworkRules: []
    ipRules: []
  }
  networkInjections: [
    {
      scenario: 'agent'
      subnetArmId: agentSubnet.id
      useMicrosoftManagedNetwork: false
    }
  ]
}

var trustedCertificateSourcesProperty = enablePrivateCaTrust ? {
  trustedCertificateSources: [
    {
      type: 'AzureKeyVault'
      resourceId: keyVault.id
      certificateBundleReferences: [
        {
          secretName: gatewayCaSecretName
          secretVersion: gatewayCaSecretVersion
        }
      ]
    }
  ]
} : {}

resource agentAccount 'Microsoft.CognitiveServices/accounts@2026-11-15-preview' = {
  name: foundryAgentAccountName
  location: location
  kind: 'AIServices'
  tags: commonTags
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: union(agentAccountBaseProperties, trustedCertificateSourcesProperty)
}

// Foundry account MI reads the root CA PEM (SECRET, getSecret) for
// trustedCertificateSources resolution. Granted in both phases so VERIFY needs only
// the flag flip.
resource kvFoundrySecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, agentAccount.id, roleKeyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: agentAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource agentAccountPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${foundryAgentAccountName}'
  location: location
  tags: commonTags
  properties: {
    subnet: {
      id: peSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-foundry-agent'
        properties: {
          privateLinkServiceId: agentAccount.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource agentAccountPeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: agentAccountPe
  name: 'foundry-account-zones'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: {
          privateDnsZoneId: privateDnsZones[0].id
        }
      }
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: privateDnsZones[1].id
        }
      }
      {
        name: 'services-ai'
        properties: {
          privateDnsZoneId: privateDnsZones[2].id
        }
      }
    ]
  }
}

// ----------------------------------------------------------------------------
// BYO agent stores (Storage / Cosmos / Search) + private endpoints.
// ----------------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: commonTags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Disabled'
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: cosmosName
  location: cosmosLocation
  tags: commonTags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: cosmosLocation
        failoverPriority: 0
      }
    ]
  }
}

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: searchName
  location: searchLocation
  tags: commonTags
  sku: {
    name: 'standard'
  }
  properties: {
    disableLocalAuth: true
    publicNetworkAccess: 'disabled'
  }
}

resource storagePe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${storageName}'
  location: location
  tags: commonTags
  properties: {
    subnet: {
      id: peSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-${storageName}'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource storagePeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: storagePe
  name: 'storage-dns'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: privateDnsZones[3].id
        }
      }
    ]
  }
}

resource cosmosPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${cosmosName}'
  location: location
  tags: commonTags
  properties: {
    subnet: {
      id: peSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-${cosmosName}'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [
            'Sql'
          ]
        }
      }
    ]
  }
}

resource cosmosPeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: cosmosPe
  name: 'cosmos-dns'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'documents'
        properties: {
          privateDnsZoneId: privateDnsZones[4].id
        }
      }
    ]
  }
}

resource searchPe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${searchName}'
  location: location
  tags: commonTags
  properties: {
    subnet: {
      id: peSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-${searchName}'
        properties: {
          privateLinkServiceId: search.id
          groupIds: [
            'searchService'
          ]
        }
      }
    ]
  }
}

resource searchPeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: searchPe
  name: 'search-dns'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'search'
        properties: {
          privateDnsZoneId: privateDnsZones[5].id
        }
      }
    ]
  }
}

// ----------------------------------------------------------------------------
// Project + BYO-store connections + RBAC + capability host + gateway
// connection.
// ----------------------------------------------------------------------------
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: agentAccount
  name: '${namePrefix}-project'
  location: location
  tags: commonTags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'BYOM private-CA repro project'
    displayName: 'BYOM Private CA'
  }
  dependsOn: [
    agentAccountPeDnsGroup
  ]
}

resource connCosmos 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: cosmosName
  properties: {
    category: 'CosmosDb'
    target: cosmos.properties.documentEndpoint
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ResourceId: cosmos.id
      location: location
    }
  }
}

resource connStorage 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: storageName
  properties: {
    category: 'AzureStorageAccount'
    target: storage.properties.primaryEndpoints.blob
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ResourceId: storage.id
      location: location
    }
  }
}

resource connSearch 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: searchName
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${searchName}.search.windows.net'
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ApiVersion: '2025-05-01-preview'
      ResourceId: search.id
      location: location
    }
  }
}

// RBAC for the project MI over the agent stores.
resource cosmosOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cosmos
  name: guid(cosmos.id, project.id, roleCosmosDbOperator)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCosmosDbOperator)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, project.id, roleStorageBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataContributor)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, project.id, roleSearchIndexDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchIndexDataContributor)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, project.id, roleSearchServiceContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchServiceContributor)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Project-level capability host bound to the BYO stores. Creating this drives
// implicit account-level cap-host provisioning (which stands up the data proxy).
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2026-05-15-preview' = {
  parent: project
  name: 'agents'
  properties: {
    // Bicep types for capabilityHosts may omit capabilityHostKind, but the ARM
    // API requires it for agent capability hosts.
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
    vectorStoreConnections: [
      searchName
    ]
    storageConnections: [
      storageName
    ]
    threadStorageConnections: [
      cosmosName
    ]
  }
  dependsOn: [
    connCosmos
    connStorage
    connSearch
    storagePeDnsGroup
    cosmosPeDnsGroup
    searchPeDnsGroup
    cosmosOperator
    storageBlobContributor
    searchIndexContributor
    searchServiceContributor
  ]
}

// Data-plane role assignments (after the cap host exists).
resource cosmosSqlDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, project.id, cosmosBuiltInDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosBuiltInDataContributorRoleId}'
    principalId: project.identity.principalId
    scope: cosmos.id
  }
  dependsOn: [
    projectCapabilityHost
  ]
}

resource storageBlobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, project.id, roleStorageBlobDataOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataOwner)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    projectCapabilityHost
  ]
}

// Connected model (ApiManagement connection) -> self-signed gateway. This is
// the leg whose inference egresses the data proxy under TLS validation.
resource connectionGateway 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: 'gateway'
  properties: {
    category: 'ApiManagement'
    target: gatewayTarget
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    audience: tokenAudience
    isSharedToAll: false
    credentials: {}
    metadata: gatewayConnectionMetadata
  }
  dependsOn: [
    projectCapabilityHost
    gatewayAci
    gatewayARecord
  ]
}

// ----------------------------------------------------------------------------
// Outputs
// ----------------------------------------------------------------------------
output resourceGroupName string = resourceGroup().name
output foundryAgentAccountName string = agentAccount.name
output projectName string = project.name
output projectPrincipalId string = project.identity.principalId
output foundryModelEndpoint string = foundryModelEndpoint
output gatewayAciName string = gatewayAci.name
output gatewayPrivateIp string = gatewayAci.properties.ipAddress.ip
output gatewayCustomDomainFqdn string = customDomainFqdn
output connectedModelTarget string = gatewayTarget
output keyVaultName string = keyVault.name
output gatewayCaSecretName string = gatewayCaSecretName
output gatewayCaSecretVersion string = gatewayCaSecretVersion
output privateCaTrustEnabled bool = enablePrivateCaTrust
output testPhaseHint string = enablePrivateCaTrust ? 'VERIFY phase: trustedCertificateSources is registered. After the account update succeeds and trust propagates automatically, verify the stored references and re-run inference (expect success).' : 'REPRO phase: trustedCertificateSources is NOT registered. Run inference through the connected model (expect certificate-not-trusted at the data proxy).'
