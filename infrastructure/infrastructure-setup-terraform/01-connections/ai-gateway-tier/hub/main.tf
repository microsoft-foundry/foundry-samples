# ============================================================================
# AI Gateway hub: deploy ONCE.
#
# Creates a Foundry account (keyless) with a model deployment and a hub project,
# then fronts the model with an AI Gateway (Microsoft.ApiManagement/aigateways):
# managed-identity provider, gateway model with a token-limit policy, a callable
# alias, and a runtime API key.
#
# Next: run ../connection once per consumer (spoke) project, in this or another
# subscription. It reads the gateway host name and key itself.
# ============================================================================

resource "random_string" "suffix" {
  length  = 5
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  create_rg           = var.existing_resource_group_name == ""
  resource_group_name = local.create_rg ? "rg-${var.name_prefix}-${random_string.suffix.result}" : var.existing_resource_group_name
  resource_group_id   = "/subscriptions/${var.subscription_id}/resourceGroups/${local.resource_group_name}"
  account_name        = "${var.name_prefix}${random_string.suffix.result}"
  gateway_name        = var.gateway_name != "" ? var.gateway_name : "${var.name_prefix}-${random_string.suffix.result}"
}

resource "azapi_resource" "resource_group" {
  count = local.create_rg ? 1 : 0

  type      = "Microsoft.Resources/resourceGroups@2024-03-01"
  name      = local.resource_group_name
  parent_id = "/subscriptions/${var.subscription_id}"
  location  = var.location
  tags      = var.tags
}

## Foundry account: system-assigned identity, local auth disabled (keyless backend).
##
resource "azapi_resource" "account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.account_name
  parent_id = local.resource_group_id
  location  = var.location
  tags      = var.tags

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
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }

  response_export_values = ["properties.endpoint"]

  # Destroyed before the purge action runs (see purge.tf).
  depends_on = [azapi_resource.resource_group, azapi_resource_action.purge_account]
}

resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.model_name
  parent_id = azapi_resource.account.id

  body = {
    sku = {
      name     = var.model_sku_name
      capacity = var.model_capacity
    }
    properties = {
      model = {
        name    = var.model_name
        format  = var.model_format
        version = var.model_version
      }
    }
  }
}

## Hub project: the admin workspace that owns the model.
##
resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  parent_id = azapi_resource.account.id
  location  = var.location
  tags      = var.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "AI Gateway hub"
      description = "Owns the model behind the centralized AI Gateway."
    }
  }

  # Serialize after the deployment: a deployment PUT briefly puts the account in a non-terminal state.
  depends_on = [azapi_resource.model_deployment]
}

## The AI Gateway in front of the model (shared module, also used by the private sample).
##
module "ai_gateway" {
  source = "../modules/ai-gateway"

  name              = local.gateway_name
  location          = var.gateway_location
  resource_group_id = local.resource_group_id
  tags              = var.tags

  foundry_account_id       = azapi_resource.account.id
  foundry_account_endpoint = azapi_resource.account.output.properties.endpoint
  model_deployment_id      = azapi_resource.model_deployment.id
  model_deployment_name    = azapi_resource.model_deployment.name
  model_version            = var.model_version

  alias_name               = var.alias_name
  tokens_per_minute        = var.tokens_per_minute
  api_key_name             = var.api_key_name
  assign_foundry_user_role = var.assign_foundry_user_role

  depends_on = [azapi_resource.resource_group]
}
