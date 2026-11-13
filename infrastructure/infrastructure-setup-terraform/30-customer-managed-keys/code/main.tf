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

## Create AI Foundry account (initially without CMK)
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.ai_foundry_name
  location  = azurerm_resource_group.rg.location
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
      customSubDomainName    = "aifoundry${random_string.unique.result}"
      disableLocalAuth       = false
      publicNetworkAccess    = "Enabled"
    }
  }
}

## Grant AI Foundry access to Key Vault
resource "azurerm_role_assignment" "kv_crypto_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Crypto User"
  principal_id         = azapi_resource.ai_foundry.identity[0].principal_id
}

## Wait for role assignment to propagate
resource "time_sleep" "wait_for_rbac" {
  depends_on      = [azurerm_role_assignment.kv_crypto_user]
  create_duration = "60s"
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

  depends_on = [time_sleep.wait_for_rbac]
}

## Create AI Foundry project
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = coalesce(var.ai_project_name, "${var.ai_foundry_name}-proj")
  location  = var.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "project"
      description = "My first project"
    }
  }

  depends_on = [azapi_update_resource.ai_foundry_cmk]
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = 1
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
