########## Create infrastructure resources
##########

## Get subscription data
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
  storage_account_name = var.create_storage_account ? (
    var.storage_account_name != "" ? var.storage_account_name : "st${random_string.unique.result}foundry"
  ) : var.storage_account_name
}

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Reference existing storage account (if not creating new)
data "azurerm_storage_account" "existing" {
  count               = var.create_storage_account ? 0 : 1
  name                = var.storage_account_name
  resource_group_name = var.storage_account_resource_group
}

## Create storage account (if requested)
resource "azurerm_storage_account" "storage" {
  count                    = var.create_storage_account ? 1 : 0
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "RAGRS"
  account_kind             = "StorageV2"

  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true # Required for AI Foundry BYOS
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

locals {
  storage_id = var.create_storage_account ? azurerm_storage_account.storage[0].id : data.azurerm_storage_account.existing[0].id
}

## Create AI Foundry account with user-owned storage
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.ai_foundry_name
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
      customSubDomainName    = var.ai_foundry_name
      disableLocalAuth       = false
      publicNetworkAccess    = "Enabled"
      userOwnedStorage = [
        {
          resourceId = local.storage_id
        }
      ]
    }
  }
}

resource "azapi_resource" "ai_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = "${var.ai_foundry_name}-proj"
  parent_id                 = azapi_resource.ai_foundry.id
  location                  = coalesce(var.foundry_location, azurerm_resource_group.rg.location)
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }

  depends_on = [time_sleep.wait_for_ai_foundry]
}

## Wait for AI Foundry creation to ensure identity is available
resource "time_sleep" "wait_for_ai_foundry" {
  depends_on      = [azapi_resource.ai_foundry]
  create_duration = "30s"
}

## Grant AI Foundry access to storage account
resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  scope                = local.storage_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id

  depends_on = [time_sleep.wait_for_ai_foundry]
}