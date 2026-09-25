// Day-2 path: PUT the named existing Project with capabilitySettings, then declare
// explicit child connections and enabled Project MI role assignments. No suffix is
// appended and no explicit CapabilityHost resource is declared. Verify the Project
// exists and the parent is already network injected; this is not a read-only reference.
// See README "Update an existing project in place" for metadata and RBAC caveats.

@description('Name of the existing AI Services (Foundry) account')
param existingAccountName string

@description('Resource group containing the AI Services account')
param accountResourceGroupName string = resourceGroup().name

@description('Subscription ID containing the AI Services account')
param accountSubscriptionId string = subscription().subscriptionId

@description('Name of the EXISTING project to reuse. No suffix is appended.')
param projectName string

@description('Azure region of the existing project. Required because scenario 22 applies capabilitySettings via a project upsert.')
param location string

@description('Display name to preserve on the existing project (pass the current value so the upsert does not change it).')
param displayName string

@description('Description written by the Project PUT. Pass the current value to preserve it; omitting this parameter uses an empty string and clears an existing description.')
param projectDescription string = ''

// The parent account must already be network injected. capabilitySettings selects
// BYO stores, not permissions. There is no projectCapHost name parameter.

@description('Set false to skip all role-assignment modules. Use this when the existing project identity is ALREADY permissioned on the backing services (a pre-permissioned production project), to avoid RoleAssignmentExists on assignments that were created under different names.')
param assignRoles bool = true

@description('Optional name for an explicit Cosmos DB connection PUT. Empty uses <cosmosName>-<project>. This does not override implicit host bindings; inspect existing managed connections before updating.')
param cosmosDBConnectionName string = ''

@description('Optional name for an explicit Storage connection PUT. Empty uses <storageName>-<project>. This does not override implicit host bindings; inspect existing managed connections before updating.')
param azureStorageConnectionName string = ''

@description('Optional name for an explicit AI Search connection PUT. Empty uses <searchName>-<project>. This does not override implicit host bindings; inspect existing managed connections before updating.')
param aiSearchConnectionName string = ''

// Existing shared resources (from your original deployment)
@description('Name of the existing AI Search service')
param existingAiSearchName string

@description('Resource group containing the AI Search service')
param aiSearchResourceGroupName string

@description('Subscription ID containing the AI Search service')
param aiSearchSubscriptionId string

@description('Name of the existing Storage Account')
param existingStorageName string

@description('Resource group containing the Storage Account')
param storageResourceGroupName string

@description('Subscription ID containing the Storage Account')
param storageSubscriptionId string

@description('Name of the existing Cosmos DB account')
param existingCosmosDBName string

@description('Resource group containing the Cosmos DB account')
param cosmosDBResourceGroupName string

@description('Subscription ID containing the Cosmos DB account')
param cosmosDBSubscriptionId string

// Deterministic suffix from the project name. Keeps connection names and role
// assignment GUIDs stable across re-runs so the deployment is idempotent.
var projectNameLower = toLower(projectName)
var connectionSuffix = '-${projectNameLower}'

// Explicit connection PUT names, not a binding override for the implicit host.
// Validate current managed connections and returned host bindings independently.
var cosmosDBConnectionNameEffective = empty(cosmosDBConnectionName) ? '${existingCosmosDBName}${connectionSuffix}' : cosmosDBConnectionName
var azureStorageConnectionNameEffective = empty(azureStorageConnectionName) ? '${existingStorageName}${connectionSuffix}' : azureStorageConnectionName
var aiSearchConnectionNameEffective = empty(aiSearchConnectionName) ? '${existingAiSearchName}${connectionSuffix}' : aiSearchConnectionName

// Reference existing AI Services account
resource account 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' existing = {
  name: existingAccountName
  scope: resourceGroup(accountSubscriptionId, accountResourceGroupName)
}

// Reference existing shared resources
resource aiSearch 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: existingAiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: existingStorageName
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
}

resource cosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: existingCosmosDBName
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
}

// Fail fast when the bring-your-own AI Search service rejects Microsoft Entra
// (AAD) data-plane auth (apiKeyOnly). The project connection below uses
// authType=AAD, so an unpatched service leaves agents failing with 403.
module validateSearchAadAuth 'modules-network-secured/validate-search-aad-auth.bicep' = {
  name: 'validate-search-aad-auth-${projectNameLower}-deployment'
  params: {
    aiSearchName: existingAiSearchName
    aiSearchResourceGroupName: aiSearchResourceGroupName
    aiSearchSubscriptionId: aiSearchSubscriptionId
  }
}

// PUT the named Project and its child connections; current metadata must be supplied.
module aiProject 'modules-network-secured/ai-existing-project-connections.bicep' = {
  name: 'ai-existing-${projectNameLower}-deployment'
  params: {
    accountName: existingAccountName
    projectName: projectName
    location: location
    displayName: displayName
    projectDescription: projectDescription

    aiSearchName: existingAiSearchName
    aiSearchServiceResourceGroupName: aiSearchResourceGroupName
    aiSearchServiceSubscriptionId: aiSearchSubscriptionId

    cosmosDBName: existingCosmosDBName
    cosmosDBSubscriptionId: cosmosDBSubscriptionId
    cosmosDBResourceGroupName: cosmosDBResourceGroupName

    azureStorageName: existingStorageName
    azureStorageSubscriptionId: storageSubscriptionId
    azureStorageResourceGroupName: storageResourceGroupName

    cosmosDBConnectionName: cosmosDBConnectionNameEffective
    azureStorageConnectionName: azureStorageConnectionNameEffective
    aiSearchConnectionName: aiSearchConnectionNameEffective
  }
  dependsOn: [
    validateSearchAadAuth
  ]
}

module formatProjectWorkspaceId 'modules-network-secured/format-project-workspace-id.bicep' = {
  name: 'format-workspace-id-${projectNameLower}-deployment'
  params: {
    projectWorkspaceId: aiProject.outputs.projectWorkspaceId
  }
}

// Assign storage account role
module storageAccountRoleAssignment 'modules-network-secured/azure-storage-account-role-assignment.bicep' = if (assignRoles) {
  name: 'storage-account-ra-${projectNameLower}-deployment'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    azureStorageName: existingStorageName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// Assign Cosmos DB account role
module cosmosAccountRoleAssignments 'modules-network-secured/cosmosdb-account-role-assignment.bicep' = if (assignRoles) {
  name: 'cosmos-account-ra-${projectNameLower}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosDBName: existingCosmosDBName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// Assign AI Search role
module aiSearchRoleAssignments 'modules-network-secured/ai-search-role-assignments.bicep' = if (assignRoles) {
  name: 'ai-search-ra-${projectNameLower}-deployment'
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
  params: {
    aiSearchName: existingAiSearchName
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
}

// No explicit project host module. Implicit provisioning requires the existing
// network-injected parent; it does not create role assignments.

// Explicit Storage account-scoped role with ABAC. assignRoles controls ALL role
// modules (default true); it is not the assignContainerRoles switch in other paths.
module storageContainersRoleAssignment 'modules-network-secured/blob-storage-container-role-assignments-unique.bicep' = if (assignRoles) {
  name: 'storage-containers-ra-${projectNameLower}-deployment'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    aiProjectPrincipalId: aiProject.outputs.projectPrincipalId
    storageName: existingStorageName
    workspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    uniqueSuffix: projectNameLower
  }
  dependsOn: [
    storageAccountRoleAssignment
  ]
}

// Explicit Cosmos SQL database grant. No explicit host dependency/readiness barrier.
module cosmosContainerRoleAssignments 'modules-network-secured/cosmos-container-role-assignments.bicep' = if (assignRoles) {
  name: 'cosmos-containers-ra-${projectNameLower}-deployment'
  scope: resourceGroup(cosmosDBSubscriptionId, cosmosDBResourceGroupName)
  params: {
    cosmosAccountName: existingCosmosDBName
    projectWorkspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    projectPrincipalId: aiProject.outputs.projectPrincipalId
  }
  dependsOn: [
    cosmosAccountRoleAssignments
    storageContainersRoleAssignment
  ]
}

// Outputs
output projectName string = aiProject.outputs.projectName
output projectPrincipalId string = aiProject.outputs.projectPrincipalId
output projectWorkspaceId string = aiProject.outputs.projectWorkspaceId
