// Day-2 scenario: wire and secure the network-secured Standard Agent setup onto an
// EXISTING AI Foundry project, reusing it in place. Unlike add-project.bicep this
// does NOT create a new project and does NOT append a random suffix: the supplied
// projectName must be an existing project under the supplied account. It layers the
// three agent connections, role assignments, and the project capability host onto
// that project, reusing every shared module. See the README section
// "Securing an Existing Project (Reuse In-Place)".

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

@description('Description to preserve on the existing project (pass the current value so the upsert does not change it).')
param projectDescription string = ''

// Scenario 22: the project capability host is implicit (created by AccountRP from
// the project's capabilitySettings). There is no projectCapHost name parameter.

@description('Set false to skip all role-assignment modules. Use this when the existing project identity is ALREADY permissioned on the backing services (a pre-permissioned production project), to avoid RoleAssignmentExists on assignments that were created under different names.')
param assignRoles bool = true

@description('Optional. Full name of the Cosmos DB connection on the project. Leave empty to use the default <cosmosName>-<project>. Set this to match a connection that already exists (for example one a portal-created capability host already binds to).')
param cosmosDBConnectionName string = ''

@description('Optional. Full name of the Storage connection on the project. Leave empty to use the default <storageName>-<project>.')
param azureStorageConnectionName string = ''

@description('Optional. Full name of the AI Search connection on the project. Leave empty to use the default <searchName>-<project>.')
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

// Effective connection names: explicit override if supplied, otherwise the
// deterministic default. Lets a customer match connections a pre-existing
// capability host already binds to.
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

// Add the agent connections to the EXISTING project (no project is created)
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

// Scenario 22: no explicit project capability-host module. AccountRP creates it
// implicitly from the project's capabilitySettings (set in the connections module).

// Assign storage container roles. The implicit capability host provisions the
// agent containers and their role assignments during create; these run only when
// assignRoles=true (e.g. to pre-assign against already-existing containers).
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

// Assign Cosmos container roles after capability host creation
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
