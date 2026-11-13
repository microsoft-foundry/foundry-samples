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

  application_insights_name            = coalesce(var.application_insights_name, "${var.ai_foundry_name}-appi")
  application_insights_connection_name = coalesce(var.application_insights_connection_name, "${local.application_insights_name}-connection")
  log_analytics_workspace_name         = coalesce(var.log_analytics_workspace_name, substr("${var.ai_foundry_name}-law", 0, 63))
}

## Create AI Foundry account with User-Assigned Identity
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.ai_foundry_name
  location  = coalesce(var.foundry_location, azurerm_resource_group.rg.location)
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
}

## Create AI Foundry project with User-Assigned Identity
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = coalesce(var.ai_project_name, "${var.ai_foundry_name}-proj")
  location  = azapi_resource.ai_foundry.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type         = "UserAssigned"
    identity_ids = [local.uai_id]
  }

  body = {
    properties = {}
  }
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  count     = var.deploy_model ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
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
}
