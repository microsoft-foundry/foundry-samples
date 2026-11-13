# One VNet-injected Foundry project. Its system-assigned MI is the principal
# the APIM gateway allowlists. Because this is a NEW project, its MI object id
# must be added to hub-allowlist/allowlist.auto.tfvars (see README step) or
# the BYOG gateway call returns 401.
resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  location  = local.location
  parent_id = azapi_resource.foundry_agent_account.id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = var.project_description
      displayName = var.project_display_name
    }
  }

  response_export_values = ["identity.principalId"]

  depends_on = [
    azapi_resource.foundry_agent_account,
    azurerm_private_endpoint.foundry_agent,
  ]
}

# Allow the project MI to replicate through Entra before RBAC.
resource "time_sleep" "wait_project_identity" {
  create_duration = "10s"
  depends_on      = [azapi_resource.project]
}

# ---- Project connections to the BYO agent stores (AAD auth) ----

resource "azapi_resource" "conn_cosmos" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.cosmos_name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category = "CosmosDb"
      target   = azurerm_cosmosdb_account.agent.endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_cosmosdb_account.agent.id
        location   = local.location
      }
    }
  }

  depends_on = [azapi_resource.project]
}

resource "azapi_resource" "conn_storage" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.storage_name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category = "AzureStorageAccount"
      target   = azurerm_storage_account.agent.primary_blob_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_storage_account.agent.id
        location   = local.location
      }
    }
  }

  depends_on = [azapi_resource.project]
}

resource "azapi_resource" "conn_search" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.search_name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category = "CognitiveSearch"
      target   = "https://${local.search_name}.search.windows.net"
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ApiVersion = "2025-05-01-preview"
        ResourceId = azapi_resource.agent_search.id
        location   = local.location
      }
    }
  }

  depends_on = [azapi_resource.project]
}

# ---- RBAC for the project MI over the agent stores ----

resource "azurerm_role_assignment" "cosmos_operator" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}${local.cosmos_name}cosmosoperator")
  scope                = azurerm_cosmosdb_account.agent.id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "storage_blob_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}${local.storage_name}blobcontributor")
  scope                = azurerm_storage_account.agent.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_index_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}${local.search_name}indexcontributor")
  scope                = azapi_resource.agent_search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_service_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}${local.search_name}servicecontributor")
  scope                = azapi_resource.agent_search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "time_sleep" "wait_rbac" {
  create_duration = "60s"
  depends_on = [
    azurerm_role_assignment.cosmos_operator,
    azurerm_role_assignment.storage_blob_contributor,
    azurerm_role_assignment.search_index_contributor,
    azurerm_role_assignment.search_service_contributor,
  ]
}

# ---- Project-level capability host bound to the BYO stores ----
# Referencing the store connections here is what completes the private-agent
# metadata the data-proxy relies on.
resource "azapi_resource" "project_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "agents"
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind       = "Agents"
      vectorStoreConnections   = [local.search_name]
      storageConnections       = [local.storage_name]
      threadStorageConnections = [local.cosmos_name]
    }
  }

  depends_on = [
    azapi_resource.conn_cosmos,
    azapi_resource.conn_storage,
    azapi_resource.conn_search,
    azurerm_private_endpoint.storage,
    azurerm_private_endpoint.cosmos,
    azurerm_private_endpoint.search,
    time_sleep.wait_rbac,
  ]
}

# ---- Data-plane role assignments (after the caphost is created) ----

resource "azurerm_cosmosdb_sql_role_assignment" "cosmos_data_contributor" {
  name                = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}cosmosdbsqlrole")
  resource_group_name = local.spoke_rg_name
  account_name        = azurerm_cosmosdb_account.agent.name
  scope               = azurerm_cosmosdb_account.agent.id
  role_definition_id  = "${azurerm_cosmosdb_account.agent.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.project.output.identity.principalId
  depends_on          = [azapi_resource.project_capability_host]
}

resource "azurerm_role_assignment" "storage_blob_owner" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.output.identity.principalId}${local.storage_name}blobowner")
  scope                = azurerm_storage_account.agent.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [azapi_resource.project_capability_host]
}

# ---- BYOG ApiManagement connection (identical to sample 47's 05) ----
# This is the connection whose Responses -> APIM egress the data-proxy sits
# in front of, now that the account is VNet-injected.
resource "azapi_resource" "connection_gateway" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = "gateway"
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "ApiManagement"
      target        = local.gateway_private_url
      authType      = "ProjectManagedIdentity"
      audience      = local.gateway_audience
      isSharedToAll = false
      credentials   = {}
      metadata      = local.gateway_connection_metadata
    }
  }

  depends_on = [azapi_resource.project_capability_host]
}

# ---- Destroy-time purge so the delegated agent subnet can be removed ----
# Injection creates /subnets/snet-agent/serviceAssociationLinks/legionservicelink.
# Purging the soft-deleted account clears the SAL so the subnet destroy does
# not hit InUseSubnetCannotBeDeleted.
resource "time_sleep" "purge_cooldown" {
  destroy_duration = "900s"
  depends_on       = [azurerm_subnet.agent]
}

resource "azapi_resource_action" "purge_foundry_agent_account" {
  method      = "DELETE"
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  resource_id = "/subscriptions/${var.spoke_subscription_id}/providers/Microsoft.CognitiveServices/locations/${local.location}/resourceGroups/${local.spoke_rg_name}/deletedAccounts/${local.foundry_agent_account_name}"
  when        = "destroy"

  depends_on = [time_sleep.purge_cooldown]
}
