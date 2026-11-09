# ============================================================================
# VNet-injected Foundry project (workload spoke), its BYO-store connections +
# RBAC, the project-level capability host, and the connected-model
# (ApiManagement) connection that targets the hub gateway hostname behind
# private DNS.
# ============================================================================

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "${var.name_prefix}-project"
  location  = var.location
  parent_id = azapi_resource.foundry_agent_account.id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = "BYOM through a private-CA hub gateway behind private DNS"
      displayName = "BYOM Private CA"
    }
  }

  response_export_values = ["identity.principalId"]

  depends_on = [
    azapi_resource.foundry_agent_account,
    azurerm_private_endpoint.foundry_agent,
  ]
}

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
        location   = var.location
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
        location   = var.location
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
        ResourceId = azurerm_search_service.agent.id
        location   = var.location
      }
    }
  }

  depends_on = [azapi_resource.project]
}

# ---- RBAC for the project MI over the agent stores ----
resource "azurerm_role_assignment" "cosmos_operator" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}${local.cosmos_name}cosmosoperator")
  scope                = azurerm_cosmosdb_account.agent.id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.project.identity[0].principal_id
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "storage_blob_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}${local.storage_name}blobcontributor")
  scope                = azurerm_storage_account.agent.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.project.identity[0].principal_id
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_index_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}${local.search_name}indexcontributor")
  scope                = azurerm_search_service.agent.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.project.identity[0].principal_id
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_service_contributor" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}${local.search_name}servicecontributor")
  scope                = azurerm_search_service.agent.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.project.identity[0].principal_id
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
# Creating this drives implicit account-level cap-host provisioning (which
# stands up the data proxy). For an injected account you must NOT create a
# manual account-level cap host.
#
# Create the host after the account identity can read the root CA secret.
# Subsequent account trust updates propagate automatically.
resource "azapi_resource" "project_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2026-05-15-preview"
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
    time_sleep.wait_foundry_kv_rbac,
    # The gateway must be available before the host's initial deployment.
    azurerm_application_gateway.gateway,
  ]
}

# ---- Data-plane role assignments (after the cap host exists) ----
resource "azurerm_cosmosdb_sql_role_assignment" "cosmos_data_contributor" {
  name                = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}cosmosdbsqlrole")
  resource_group_name = local.rg_name
  account_name        = azurerm_cosmosdb_account.agent.name
  scope               = azurerm_cosmosdb_account.agent.id
  role_definition_id  = "${azurerm_cosmosdb_account.agent.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.project.identity[0].principal_id
  depends_on          = [azapi_resource.project_capability_host]
}

resource "azurerm_role_assignment" "storage_blob_owner" {
  name                 = uuidv5("dns", "${azapi_resource.project.name}${azapi_resource.project.identity[0].principal_id}${local.storage_name}blobowner")
  scope                = azurerm_storage_account.agent.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.project.identity[0].principal_id
  depends_on           = [azapi_resource.project_capability_host]
}

# ---- Connected model (ApiManagement connection) -> hub gateway ----
# The data proxy carries this connection's inference egress. Its target is the
# gateway hostname behind private DNS, so the data proxy validates the
# gateway's private-CA certificate against trustedCertificateSources.
resource "azapi_resource" "connection_gateway" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = "gateway"
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "ApiManagement"
      target        = local.gateway_target
      authType      = "ProjectManagedIdentity"
      audience      = local.token_audience
      isSharedToAll = false
      credentials   = {}
      metadata      = local.gateway_connection_metadata
    }
  }

  depends_on = [
    azapi_resource.project_capability_host,
    azurerm_api_management_api_policy.inference,
    azurerm_application_gateway.gateway,
    azurerm_private_dns_a_record.gateway,
  ]
}
