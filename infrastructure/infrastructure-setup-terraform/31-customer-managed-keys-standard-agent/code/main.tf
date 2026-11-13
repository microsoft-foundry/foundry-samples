########## Create infrastructure resources with CMK and Standard Agent
##########

## Get current client and subscription data
data "azurerm_client_config" "current" {}

## Create a random string for unique naming
resource "random_string" "unique" {
  length      = 4
  min_numeric = 4
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

locals {
  account_name = lower("${var.ai_services_name_prefix}${random_string.unique.result}")
}

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Create Key Vault with soft delete and purge protection for CMK
resource "azurerm_key_vault" "kv" {
  name                       = "kv-${random_string.unique.result}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = true
  rbac_authorization_enabled = true
}

## Grant the deployer Key Vault Administrator to create keys
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

## Create encryption key in Key Vault
resource "azurerm_key_vault_key" "cmk" {
  name         = "cmk-encryption-key"
  key_vault_id = azurerm_key_vault.kv.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["decrypt", "encrypt", "sign", "unwrapKey", "verify", "wrapKey"]

  depends_on = [azurerm_role_assignment.kv_admin]
}

## Create Storage Account for standard agent
resource "azurerm_storage_account" "storage" {
  name                     = "aifoundry${random_string.unique.result}stor"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "ZRS"

  shared_access_key_enabled       = false
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }
}

## Create AI Search for standard agent
resource "azurerm_search_service" "search" {
  name                = replace("aifoundry-${random_string.unique.result}-search", "_", "-")
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "standard"

  local_authentication_enabled  = true
  authentication_failure_mode   = "http401WithBearerChallenge"
  public_network_access_enabled = true
}

## Create Cosmos DB for standard agent
resource "azurerm_cosmosdb_account" "cosmos" {
  name                = "aifoundry${random_string.unique.result}cosmos"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  public_network_access_enabled = true
}

## Create AI Foundry account (initially without CMK)
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = local.account_name
  location  = coalesce(var.foundry_location, azurerm_resource_group.rg.location)
  parent_id = azurerm_resource_group.rg.id

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
      publicNetworkAccess    = "Enabled"
      disableLocalAuth       = false
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }
}

## Wait for AI Foundry identity to be available
resource "time_sleep" "wait_for_identity" {
  depends_on      = [azapi_resource.ai_foundry]
  create_duration = "30s"
}

## Grant AI Foundry identity access to Key Vault for encryption
resource "azurerm_role_assignment" "kv_crypto_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Crypto User"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id

  depends_on = [time_sleep.wait_for_identity]
}

## Wait for Key Vault permissions to propagate
resource "time_sleep" "wait_for_kv_permissions" {
  depends_on      = [azurerm_role_assignment.kv_crypto_user]
  create_duration = "30s"
}

## Update AI Foundry with CMK encryption
resource "azapi_update_resource" "ai_foundry_cmk" {
  type        = "Microsoft.CognitiveServices/accounts@2025-06-01"
  resource_id = azapi_resource.ai_foundry.id

  body = {
    properties = {
      encryption = {
        keySource = "Microsoft.KeyVault"
        keyVaultProperties = {
          keyName     = azurerm_key_vault_key.cmk.name
          keyVersion  = azurerm_key_vault_key.cmk.version
          keyVaultUri = azurerm_key_vault.kv.vault_uri
        }
      }
    }
  }

  depends_on = [time_sleep.wait_for_kv_permissions]
}

## Grant AI Foundry access to Storage
resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry access to AI Search
resource "azurerm_role_assignment" "search_index_data_contributor" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

resource "azurerm_role_assignment" "search_service_contributor" {
  scope                = azurerm_search_service.search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Grant AI Foundry access to Cosmos DB
resource "azurerm_cosmosdb_sql_role_assignment" "cosmos_contributor" {
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_foundry.identity[0].principal_id
  scope               = azurerm_cosmosdb_account.cosmos.id
}

## Wait for role assignments to propagate
resource "time_sleep" "wait_for_rbac" {
  depends_on = [
    azurerm_role_assignment.storage_blob_data_contributor,
    azurerm_role_assignment.search_index_data_contributor,
    azurerm_role_assignment.search_service_contributor,
    azurerm_cosmosdb_sql_role_assignment.cosmos_contributor
  ]
  create_duration = "60s"
}

## Create AI Foundry project
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  location  = azapi_resource.ai_foundry.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }

  depends_on = [
    time_sleep.wait_for_rbac,
    azapi_update_resource.ai_foundry_cmk
  ]
}

## Create connections
resource "azapi_resource" "storage_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  name                      = "storage-connection"
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AzureStorageAccount"
      target        = azurerm_storage_account.storage.primary_blob_endpoint
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_storage_account.storage.id
        location   = var.location
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}

resource "azapi_resource" "search_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  name                      = "search-connection"
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "CognitiveSearch"
      target        = "https://${azurerm_search_service.search.name}.search.windows.net"
      authType      = "AAD"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        ApiVersion = "2025-05-01-preview"
        ResourceId = azurerm_search_service.search.id
        location   = var.location
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = var.model_capacity
      name     = "GlobalStandard"
    }
    properties = {
      model = {
        name    = var.model_name
        format  = "OpenAI"
        version = var.model_version
      }
    }
  }

  depends_on = [azapi_resource.ai_project]
}

## Set up capability hosts for agent support
resource "azapi_resource" "account_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview"
  name                      = "${local.account_name}-capHost"
  parent_id                 = azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind = "Agents"
    }
  }

  depends_on = [
    azapi_resource.ai_project,
    azapi_resource.storage_connection,
    azapi_resource.search_connection
  ]
}

resource "azapi_resource" "project_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "${var.project_name}-capHost"
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind     = "Agents"
      storageConnections     = ["storage-connection"]
      vectorStoreConnections = ["search-connection"]
    }
  }

  depends_on = [azapi_resource.account_capability_host]
}
