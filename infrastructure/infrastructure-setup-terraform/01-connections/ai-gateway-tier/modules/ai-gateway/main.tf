# ============================================================================
# AI Gateway (Microsoft.ApiManagement/aigateways) fronting one Foundry model.
#
# Creates the gateway with a system-assigned identity, grants that identity
# Foundry User on the backend account (keyless backend), registers a Foundry
# model provider + the deployment as a gateway model with a token-limit policy,
# publishes a callable alias, and creates a runtime API key.
#
# Uses the aigateways resource type, which replaced the deprecated
# Microsoft.ApiManagement/service + AIGateway SKU (no new creates since
# 2026-10-14; retired 2027-01-15). Shapes and API version mirror the official
# labs: https://github.com/Azure/aigateway/tree/main/labs
# ============================================================================

locals {
  api_version             = "2025-09-01-preview"
  foundry_user_role_id    = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  foundry_subscription_id = split("/", var.foundry_account_id)[2]
  foundry_endpoint        = endswith(var.foundry_account_endpoint, "/") ? var.foundry_account_endpoint : "${var.foundry_account_endpoint}/"
  alias_name              = coalesce(var.alias_name, var.model_deployment_name)

  # Empty when backend_subnet_id is null, so a public-routing gateway sends properties = {}.
  gateway_backend = {
    for k, v in { backend = { subnet = { id = var.backend_subnet_id } } } : k => v if var.backend_subnet_id != null
  }
}

resource "azapi_resource" "gateway" {
  type                      = "Microsoft.ApiManagement/aigateways@${local.api_version}"
  name                      = var.name
  parent_id                 = var.resource_group_id
  location                  = var.location
  tags                      = var.tags
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  # sku is omitted so the resource provider applies its default, as the official labs do.
  # backend.subnet can only be set when the gateway is created.
  body = {
    properties = local.gateway_backend
  }

  response_export_values = ["properties.frontend.defaultHostname"]

  timeouts {
    create = "60m"
    delete = "60m"
  }
}

## Keyless backend: the gateway's managed identity calls Foundry as Foundry User.
##
resource "azapi_resource" "foundry_user" {
  count = var.assign_foundry_user_role ? 1 : 0

  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5("url", "${var.foundry_account_id}/${azapi_resource.gateway.id}/${local.foundry_user_role_id}")
  parent_id = var.foundry_account_id

  body = {
    properties = {
      principalId      = azapi_resource.gateway.identity[0].principal_id
      principalType    = "ServicePrincipal"
      roleDefinitionId = "/subscriptions/${local.foundry_subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
    }
  }
}

resource "time_sleep" "wait_rbac" {
  depends_on      = [azapi_resource.foundry_user]
  create_duration = var.rbac_propagation_wait
}

## The 'default' workspace is created with the gateway and holds providers, models, and aliases.
##
resource "azapi_resource" "model_provider" {
  type                      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@${local.api_version}"
  name                      = var.provider_name
  parent_id                 = "${azapi_resource.gateway.id}/workspaces/default"
  schema_validation_enabled = false

  body = {
    properties = {
      kind        = "Foundry"
      displayName = "Foundry"
      description = "Foundry account imported over the gateway's managed identity."
      foundry = {
        endpoint    = local.foundry_endpoint
        resourceIds = [var.foundry_account_id]
        authentication = {
          kind = "ManagedIdentity"
          managedIdentity = {
            resource = "https://cognitiveservices.azure.com/"
          }
        }
      }
    }
  }

  depends_on = [time_sleep.wait_rbac]
}

resource "azapi_resource" "model" {
  type                      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@${local.api_version}"
  name                      = var.model_deployment_name
  parent_id                 = azapi_resource.model_provider.id
  schema_validation_enabled = false

  body = {
    properties = {
      displayName = var.model_deployment_name
      apiFormat   = "OpenAIChatCompletions"
      supportedEndpoints = [
        "/openai/v1/chat/completions",
        "/openai/v1/responses"
      ]
      deployment = {
        resourceId   = var.model_deployment_id
        modelName    = var.model_deployment_name
        modelVersion = var.model_version
      }
      policies = [
        {
          type       = "tokenLimit"
          period     = "minute"
          count      = var.tokens_per_minute
          counterKey = ["identity"]
        }
      ]
    }
  }
}

## The alias is the stable name callers send in the request "model" field.
##
resource "azapi_resource" "alias" {
  type                      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@${local.api_version}"
  name                      = local.alias_name
  parent_id                 = "${azapi_resource.gateway.id}/workspaces/default"
  schema_validation_enabled = false

  body = {
    properties = {
      aliasName = local.alias_name
      backendModels = [
        {
          resourceId = azapi_resource.model.id
        }
      ]
    }
  }
}

## Runtime key sent by callers as "Authorization: Bearer <key>". Its value is never an output.
##
resource "azapi_resource" "api_key" {
  type                      = "Microsoft.ApiManagement/aigateways/apiKeys@${local.api_version}"
  name                      = var.api_key_name
  parent_id                 = azapi_resource.gateway.id
  schema_validation_enabled = false

  body = {
    properties = {
      displayName = "Foundry connection key"
    }
  }

  response_export_values = ["name"]
}
