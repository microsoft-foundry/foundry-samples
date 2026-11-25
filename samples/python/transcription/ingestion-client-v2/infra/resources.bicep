@description('Primary location for all resources.')
param location string

@description('Unique token used to build globally-unique resource names.')
param resourceToken string

@description('Environment name, embedded into storage account names for readability.')
param environmentName string

@description('Tags applied to every resource.')
param tags object

param enableNetworkIsolation bool
param enableStorageLifecycle bool

@description('Optional principal ID granted data-plane access for testing (upload audio, read results).')
param deployerPrincipalId string

// Container names (kept in one place so code + infra agree)
var audioInputContainer = 'audio-input'
var configContainer = 'config'
var quarantineContainer = 'quarantine'
var transcriptionsContainer = 'transcriptions'
var errorsContainer = 'errors'
var batchJobsContainer = 'batch-jobs'
var batchPendingContainer = 'batch-pending'
var jobsQueueName = 'transcription-jobs'
var publicNetworkAccess = enableNetworkIsolation ? 'Disabled' : 'Enabled'

// Human-readable storage account names: st<purpose><env><shorthash>
// (lowercase alphanumeric, <=24 chars, globally unique). env is sanitized + capped so the
// name stays valid for any environmentName; the 6-char hash preserves global uniqueness.
var envSlug = take(toLower(replace(replace(environmentName, '-', ''), '_', '')), 8)
var storageSuffix = '${envSlug}${take(resourceToken, 6)}'

// Built-in role definition IDs
var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  serviceBusDataReceiver: '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
  serviceBusDataSender: '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  storageBlobDelegator: 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a'
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${resourceToken}'
  location: location
  tags: tags
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// Dedicated storage account for the Functions runtime (host + deployment package)
resource funcStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stfunc${storageSuffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Enabled'
  }
}

resource funcStorageBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: funcStorage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: funcStorageBlob
  name: 'deploymentpackage'
}

// Input (audio) storage account
resource inputStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stinput${storageSuffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: publicNetworkAccess
  }
}

resource inputBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: inputStorage
  name: 'default'
}

resource audioInput 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: inputBlob
  name: audioInputContainer
}

resource configStore 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: inputBlob
  name: configContainer
}

resource quarantine 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: inputBlob
  name: quarantineContainer
}

// Output (results) storage account
resource outputStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stoutput${storageSuffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: publicNetworkAccess
  }
}

resource outputBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: outputStorage
  name: 'default'
}

resource transcriptions 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: outputBlob
  name: transcriptionsContainer
}

resource errors 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: outputBlob
  name: errorsContainer
}

// Tracks in-flight batch jobs for the completion poller.
resource batchJobs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: outputBlob
  name: batchJobsContainer
}

// Files awaiting aggregation into a multi-file batch job.
resource batchPending 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: outputBlob
  name: batchPendingContainer
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = if (enableStorageLifecycle) {
  parent: inputStorage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'tier-and-expire-audio'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${audioInputContainer}/'
              ]
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 30
                }
                delete: {
                  daysAfterModificationGreaterThan: 365
                }
              }
            }
          }
        }
      ]
    }
  }
}

resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'sb-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: true
  }
}

resource jobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: jobsQueueName
  properties: {
    requiresDuplicateDetection: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 10
    lockDuration: 'PT5M'
    defaultMessageTimeToLive: 'P1D'
  }
}

// Foundry (multi-service AI Services) resource used for all Speech-to-text engines
resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'aif-${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: 'aif-${resourceToken}'
    publicNetworkAccess: publicNetworkAccess
    disableLocalAuth: true
  }
}

resource flexPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${resourceToken}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: 'func-${resourceToken}'
  location: location
  tags: union(tags, {
    'azd-service-name': 'functions'
  })
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    serverFarmId: flexPlan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${funcStorage.properties.primaryEndpoints.blob}${deploymentContainer.name}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identity.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 100
        instanceMemoryMB: 4096
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: funcStorage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'AzureWebJobsStorage__clientId'
          value: identity.properties.clientId
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'ServiceBusConnection__fullyQualifiedNamespace'
          value: '${serviceBus.name}.servicebus.windows.net'
        }
        {
          name: 'ServiceBusConnection__credential'
          value: 'managedidentity'
        }
        {
          name: 'ServiceBusConnection__clientId'
          value: identity.properties.clientId
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: identity.properties.clientId
        }
        {
          name: 'INPUT_STORAGE_BLOB_ENDPOINT'
          value: inputStorage.properties.primaryEndpoints.blob
        }
        {
          name: 'OUTPUT_STORAGE_BLOB_ENDPOINT'
          value: outputStorage.properties.primaryEndpoints.blob
        }
        {
          name: 'FOUNDRY_ENDPOINT'
          value: foundry.properties.endpoint
        }
        {
          name: 'SERVICE_BUS_QUEUE'
          value: jobsQueueName
        }
        {
          name: 'AUDIO_INPUT_CONTAINER'
          value: audioInputContainer
        }
        {
          name: 'CONFIG_CONTAINER'
          value: configContainer
        }
        {
          name: 'QUARANTINE_CONTAINER'
          value: quarantineContainer
        }
        {
          name: 'OUTPUT_CONTAINER'
          value: transcriptionsContainer
        }
        {
          name: 'ERRORS_CONTAINER'
          value: errorsContainer
        }
        {
          name: 'BATCH_JOBS_CONTAINER'
          value: batchJobsContainer
        }
        {
          name: 'BATCH_PENDING_CONTAINER'
          value: batchPendingContainer
        }
        {
          name: 'MAX_FILES_PER_JOB'
          value: '100'
        }
        {
          name: 'MAX_DELIVERY_COUNT'
          value: string(jobsQueue.properties.maxDeliveryCount)
        }
      ]
    }
  }
}

// Event Grid: blob-created on the input account -> Service Bus queue (keyless via topic identity)
resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' = {
  name: 'evgt-${resourceToken}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    source: inputStorage.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

resource topicSbSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus
  name: guid(serviceBus.id, systemTopic.id, roles.serviceBusDataSender)
  properties: {
    principalId: systemTopic.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataSender)
    principalType: 'ServicePrincipal'
  }
}

resource blobCreatedSub 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2024-06-01-preview' = {
  parent: systemTopic
  name: 'audio-created'
  properties: {
    deliveryWithResourceIdentity: {
      identity: {
        type: 'SystemAssigned'
      }
      destination: {
        endpointType: 'ServiceBusQueue'
        properties: {
          resourceId: jobsQueue.id
        }
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/${audioInputContainer}/'
    }
    eventDeliverySchema: 'EventGridSchema'
    retryPolicy: {
      maxDeliveryAttempts: 30
      eventTimeToLiveInMinutes: 1440
    }
  }
  dependsOn: [
    topicSbSender
  ]
}

// Role assignments for the Function's managed identity
resource miInputBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: inputStorage
  name: guid(inputStorage.id, identity.id, roles.storageBlobDataContributor)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'ServicePrincipal'
  }
}

resource miOutputBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: outputStorage
  name: guid(outputStorage.id, identity.id, roles.storageBlobDataContributor)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'ServicePrincipal'
  }
}

resource miFuncBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: funcStorage
  name: guid(funcStorage.id, identity.id, roles.storageBlobDataOwner)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
    principalType: 'ServicePrincipal'
  }
}

resource miServiceBus 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus
  name: guid(serviceBus.id, identity.id, roles.serviceBusDataReceiver)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataReceiver)
    principalType: 'ServicePrincipal'
  }
}

// Needed to mint short-lived user-delegation SAS (keyless) for batch transcription contentUrls.
resource miInputDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: inputStorage
  name: guid(inputStorage.id, identity.id, roles.storageBlobDelegator)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDelegator)
    principalType: 'ServicePrincipal'
  }
}

resource miFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, identity.id, roles.cognitiveServicesUser)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
    principalType: 'ServicePrincipal'
  }
}

// NOTE: the Foundry identity intentionally has NO storage role assignments. Batch reads
// audio via short-lived user-delegation SAS in contentUrls, and results are pulled by the
// poller - so Foundry never accesses our storage accounts directly (least privilege).

// Optional: grant the deployer data-plane access for testing (upload audio, seed config, read results)
resource deployerInputBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: inputStorage
  name: guid(inputStorage.id, deployerPrincipalId, roles.storageBlobDataContributor)
  properties: {
    principalId: deployerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'User'
  }
}

resource deployerOutputBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: outputStorage
  name: guid(outputStorage.id, deployerPrincipalId, roles.storageBlobDataContributor)
  properties: {
    principalId: deployerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'User'
  }
}

// The deployer (azd) uploads the function package to the runtime storage account
// over Azure AD (shared keys are disabled), so it needs blob data access there too.
resource deployerFuncBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: funcStorage
  name: guid(funcStorage.id, deployerPrincipalId, roles.storageBlobDataContributor)
  properties: {
    principalId: deployerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'User'
  }
}

resource dashboard 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid('workbook', resourceToken)
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'Ingestion Client v2 - Transcription Monitoring'
    category: 'workbook'
    sourceId: appInsights.id
    serializedData: loadTextContent('dashboard.workbook.json')
  }
}

output functionAppName string = functionApp.name
output inputStorageAccountName string = inputStorage.name
output outputStorageAccountName string = outputStorage.name
output audioInputContainer string = audioInputContainer
output configContainer string = configContainer
output foundryEndpoint string = foundry.properties.endpoint
