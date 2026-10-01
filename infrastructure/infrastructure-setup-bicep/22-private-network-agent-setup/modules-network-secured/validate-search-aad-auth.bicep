// Fail-fast guard for a bring-your-own Azure AI Search service.
//
// Foundry creates its CognitiveSearch connection with authType=AAD. A Search
// service only accepts Microsoft Entra (AAD) data-plane tokens when local auth
// is disabled OR when authOptions contains an aadOrApiKey block. The Azure
// default for a new Search service is apiKeyOnly (local auth on, authOptions
// null), which rejects AAD and surfaces as a misleading 403 "you do not have
// permissions" on the agent. A newly created Search service in this sample sets
// authOptions for you; an existing one you bring may not, so this module reads
// the live state and stops the deployment with an actionable message instead of
// letting it succeed with broken agents.

@description('Name of the existing AI Search service to validate.')
param aiSearchName string

@description('Resource group containing the existing AI Search service.')
param aiSearchResourceGroupName string = resourceGroup().name

@description('Subscription ID containing the existing AI Search service.')
param aiSearchSubscriptionId string = subscription().subscriptionId

resource aiSearch 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

// A missing disableLocalAuth defaults to false (local auth enabled), and a
// missing authOptions means no AAD block is present.
var localAuthDisabled = aiSearch.properties.?disableLocalAuth ?? false
var aadOptionPresent = contains(aiSearch.properties.?authOptions ?? {}, 'aadOrApiKey')

// AAD is broken only in the apiKeyOnly state: local auth still enabled and no
// aadOrApiKey block to fall back on.
var aadAuthBroken = !localAuthDisabled && !aadOptionPresent

output searchAadAuthStatus string = aadAuthBroken
  ? fail('Existing Azure AI Search service "${aiSearchName}" rejects Microsoft Entra (AAD) data-plane authentication (apiKeyOnly). Foundry connects to Search with authType=AAD, so agents will fail with HTTP 403. Enable AAD on the service, then redeploy. Fix: az search service update --name ${aiSearchName} --resource-group ${aiSearchResourceGroupName} --subscription ${aiSearchSubscriptionId} --auth-options aadOrApiKey --aad-auth-failure-mode http401WithBearerChallenge')
  : 'ok'
