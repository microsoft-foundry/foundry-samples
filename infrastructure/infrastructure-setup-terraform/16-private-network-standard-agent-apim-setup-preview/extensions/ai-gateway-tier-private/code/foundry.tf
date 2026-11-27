########## The agent's Foundry account and project (the "spoke")
##########
## Private, VNet-injected Foundry account + project + capability host, following
## ../../../../15a-private-network-standard-agent-setup. The agent's model comes
## from the gateway connection (gateway.tf), so this account has no deployment.

resource "azapi_resource" "foundry" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = local.account_name
  parent_id                 = azurerm_resource_group.rg.id
  location                  = var.location
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.account_name
      disableLocalAuth       = false

      # Private by default. foundry_allowed_ip_ranges / foundry_public_network_access_enabled
      # open the account (Entra auth still required) for testing without a jumpbox.
      publicNetworkAccess = local.public_access ? "Enabled" : "Disabled"
      networkAcls = {
        defaultAction = local.allow_client_ips ? "Deny" : "Allow"
        bypass        = "AzureServices"
        ipRules       = [for ip in var.foundry_allowed_ip_ranges : { value = trimsuffix(ip, "/32") }]
      }

      networkInjections = [
        {
          scenario                   = "agent"
          subnetArmId                = azurerm_subnet.agent.id
          useMicrosoftManagedNetwork = false
        }
      ]
    }
  }

  # Destroyed before the purge action runs (see purge.tf).
  depends_on = [azapi_resource_action.purge_foundry]
}

resource "azapi_resource" "project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = "project${local.suffix}"
  parent_id                 = azapi_resource.foundry.id
  location                  = var.location
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "AI Gateway private project"
      description = "Network-secured agent project that consumes a model through the AI Gateway."
    }
  }

  response_export_values = ["identity.principalId", "properties.internalId"]

  depends_on = [
    azurerm_private_endpoint.storage,
    azurerm_private_endpoint.cosmosdb,
    azurerm_private_endpoint.ai_search,
    azurerm_private_endpoint.foundry,
  ]
}

resource "time_sleep" "wait_project_identity" {
  depends_on      = [azapi_resource.project]
  create_duration = "10s"
}

## Project connections to the agent data stores
##
resource "azapi_resource" "conn_cosmosdb" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = azurerm_cosmosdb_account.cosmosdb.name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  # Connections on the same project can conflict when changed in parallel (etag).
  retry = {
    error_message_regex = ["TransientError", "Etag conflict"]
  }

  body = {
    properties = {
      category = "CosmosDb"
      target   = azurerm_cosmosdb_account.cosmosdb.endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_cosmosdb_account.cosmosdb.id
        location   = var.location
      }
    }
  }
}

resource "azapi_resource" "conn_storage" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = azurerm_storage_account.storage.name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  # Connections on the same project can conflict when changed in parallel (etag).
  retry = {
    error_message_regex = ["TransientError", "Etag conflict"]
  }

  body = {
    properties = {
      category = "AzureStorageAccount"
      target   = azurerm_storage_account.storage.primary_blob_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_storage_account.storage.id
        location   = var.location
      }
    }
  }
}

resource "azapi_resource" "conn_aisearch" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = azapi_resource.ai_search.name
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  # Connections on the same project can conflict when changed in parallel (etag).
  retry = {
    error_message_regex = ["TransientError", "Etag conflict"]
  }

  body = {
    properties = {
      category = "CognitiveSearch"
      target   = "https://${azapi_resource.ai_search.name}.search.windows.net"
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ApiVersion = "2025-05-01-preview"
        ResourceId = azapi_resource.ai_search.id
        location   = var.location
      }
    }
  }
}

## Project identity roles on the data stores (before the capability host)
##
resource "azurerm_role_assignment" "cosmosdb_operator" {
  scope                = azurerm_cosmosdb_account.cosmosdb.id
  role_definition_name = "Cosmos DB Operator"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_index_data_contributor" {
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "azurerm_role_assignment" "search_service_contributor" {
  scope                = azapi_resource.ai_search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.project.output.identity.principalId
  depends_on           = [time_sleep.wait_project_identity]
}

resource "time_sleep" "wait_rbac" {
  depends_on = [
    azurerm_role_assignment.cosmosdb_operator,
    azurerm_role_assignment.storage_blob_data_contributor,
    azurerm_role_assignment.search_index_data_contributor,
    azurerm_role_assignment.search_service_contributor,
  ]
  create_duration = "60s"
}

## Capability host (the agent runtime)
##
resource "azapi_resource" "capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "caphostproj"
  parent_id                 = azapi_resource.project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind       = "Agents"
      vectorStoreConnections   = [azapi_resource.ai_search.name]
      storageConnections       = [azurerm_storage_account.storage.name]
      threadStorageConnections = [azurerm_cosmosdb_account.cosmosdb.name]
    }
  }

  depends_on = [
    azapi_resource.conn_aisearch,
    azapi_resource.conn_cosmosdb,
    azapi_resource.conn_storage,
    time_sleep.wait_rbac,
  ]
}

## Data-plane roles on containers the capability host creates (after it exists)
##
resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_data_contributor" {
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmosdb.name
  scope               = azurerm_cosmosdb_account.cosmosdb.id
  role_definition_id  = "${azurerm_cosmosdb_account.cosmosdb.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.project.output.identity.principalId
  depends_on          = [azapi_resource.capability_host]
}

resource "azurerm_role_assignment" "storage_blob_data_owner" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.project.output.identity.principalId
  condition_version    = "2.0"
  condition            = <<-EOT
  (
    (
      !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'})
      AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'})
      AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})
    )
    OR
    (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '${local.project_id_guid}'
    AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent')
  )
  EOT
  depends_on           = [azapi_resource.capability_host]
}
