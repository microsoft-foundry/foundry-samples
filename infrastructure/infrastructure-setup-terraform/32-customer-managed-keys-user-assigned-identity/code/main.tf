########## Create infrastructure with CMK and User-Assigned Identity
##########

## NOTE: User-Assigned Identity with CMK has limitations
## This setup demonstrates the pattern but may not be supported for all scenarios

## Get current client config
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

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Reference existing User-Assigned Identity (if not creating new)
data "azurerm_user_assigned_identity" "existing" {
  count               = var.create_user_assigned_identity ? 0 : 1
  name                = var.user_assigned_identity_name
  resource_group_name = var.user_assigned_identity_resource_group
}

## Create new User-Assigned Identity (if requested)
resource "azurerm_user_assigned_identity" "uai" {
  count               = var.create_user_assigned_identity ? 1 : 0
  name                = var.user_assigned_identity_name
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
}

locals {
  uai_id           = var.create_user_assigned_identity ? azurerm_user_assigned_identity.uai[0].id : data.azurerm_user_assigned_identity.existing[0].id
  uai_principal_id = var.create_user_assigned_identity ? azurerm_user_assigned_identity.uai[0].principal_id : data.azurerm_user_assigned_identity.existing[0].principal_id
  uai_client_id    = var.create_user_assigned_identity ? azurerm_user_assigned_identity.uai[0].client_id : data.azurerm_user_assigned_identity.existing[0].client_id
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

## Grant UAI access to Key Vault for encryption
resource "azurerm_role_assignment" "uai_kv_crypto" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Crypto User"
  principal_id         = local.uai_principal_id
}

## Wait for Key Vault permissions
resource "time_sleep" "wait_for_kv_permissions" {
  depends_on      = [azurerm_role_assignment.uai_kv_crypto]
  create_duration = "30s"
}

## Create AI Foundry account with User-Assigned Identity (initially without CMK)
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.ai_foundry_name
  location  = azurerm_resource_group.rg.location
  parent_id = azurerm_resource_group.rg.id

  identity {
    type         = "UserAssigned"
    identity_ids = [local.uai_id]
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
    }
  }

  depends_on = [time_sleep.wait_for_kv_permissions]
}

## Update AI Foundry with CMK encryption
## NOTE: UAI + CMK may have limitations depending on the service configuration
resource "azapi_update_resource" "ai_foundry_cmk" {
  type        = "Microsoft.CognitiveServices/accounts@2025-06-01"
  resource_id = azapi_resource.ai_foundry.id

  body = {
    properties = {
      encryption = {
        keySource = "Microsoft.KeyVault"
        keyVaultProperties = {
          identityClientId = local.uai_client_id
          keyName          = azurerm_key_vault_key.cmk.name
          keyVersion       = azurerm_key_vault_key.cmk.version
          keyVaultUri      = azurerm_key_vault.kv.vault_uri
        }
      }
    }
  }
}

## Create AI Foundry project with User-Assigned Identity
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = coalesce(var.ai_project_name, "${var.ai_foundry_name}-proj")
  location  = var.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type         = "UserAssigned"
    identity_ids = [local.uai_id]
  }

  body = {
    properties = {
      displayName = "CMK UAI Project"
      description = "Project with Customer-Managed Keys and User-Assigned Identity"
    }
  }

  depends_on = [azapi_update_resource.ai_foundry_cmk]
}
