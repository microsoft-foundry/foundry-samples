# ============================================================================
# ApiManagement connection from a Foundry project to an API in Azure API
# Management.
#
# Terraform version of
# infrastructure-setup-bicep/01-connections/apim/connection-apim.bicep: the same
# inputs produce the same connection. The target is the APIM gateway URL plus
# the API's path. With ApiKey, the APIM subscription key is read at apply time
# and sent as a write-only value, so it's never stored in state or plan files.
# ============================================================================

data "azapi_resource" "apim" {
  type                   = "Microsoft.ApiManagement/service@2024-05-01"
  resource_id            = var.apim_resource_id
  response_export_values = ["properties.gatewayUrl"]
}

data "azapi_resource" "api" {
  type                   = "Microsoft.ApiManagement/service/apis@2024-05-01"
  resource_id            = "${var.apim_resource_id}/apis/${var.api_name}"
  response_export_values = ["properties.path"]
}

ephemeral "azapi_resource_action" "subscription_keys" {
  count = var.auth_type == "ApiKey" ? 1 : 0

  type                   = "Microsoft.ApiManagement/service/subscriptions@2024-05-01"
  resource_id            = "${var.apim_resource_id}/subscriptions/${var.apim_subscription_name}"
  action                 = "listSecrets"
  method                 = "POST"
  response_export_values = ["primaryKey"]
}

locals {
  apim_service_name   = split("/", var.apim_resource_id)[8]
  connection_name     = var.connection_name != "" ? var.connection_name : "apim-${local.apim_service_name}-${var.api_name}"
  target_url          = "${data.azapi_resource.apim.output.properties.gatewayUrl}/${data.azapi_resource.api.output.properties.path}"
  has_model_discovery = var.model_discovery != null
  has_static_models   = length(var.static_models) > 0

  metadata = merge(
    { deploymentInPath = tostring(var.deployment_in_path) },
    var.inference_api_version != "" ? { inferenceAPIVersion = var.inference_api_version } : {},
    var.deployment_api_version != "" ? { deploymentAPIVersion = var.deployment_api_version } : {},
    local.has_model_discovery ? {
      modelDiscovery = jsonencode({
        listModelsEndpoint = var.model_discovery.list_models_endpoint
        getModelEndpoint   = var.model_discovery.get_model_endpoint
        deploymentProvider = var.model_discovery.deployment_provider
      })
    } : {},
    local.has_static_models ? {
      # A model's version is left out when it isn't set.
      models = jsonencode([for m in var.static_models : {
        name       = m.name
        properties = { model = { for k, v in m.properties.model : k => v if v != null } }
      }])
    } : {},
    length(var.custom_headers) > 0 ? { customHeaders = jsonencode(var.custom_headers) } : {},
    length(var.auth_config) > 0 ? { authConfig = jsonencode(var.auth_config) } : {},
  )

  # A project managed identity connection requests tokens for this audience and has no stored credentials.
  managed_identity_properties = {
    for k, v in { audience = "https://cognitiveservices.azure.com", credentials = {} } : k => v
    if var.auth_type == "ProjectManagedIdentity"
  }
}

resource "azapi_resource" "connection" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.connection_name
  parent_id                 = var.project_resource_id
  schema_validation_enabled = false

  body = {
    properties = merge(
      {
        category      = "ApiManagement"
        target        = local.target_url
        authType      = var.auth_type
        isSharedToAll = var.is_shared_to_all
        metadata      = local.metadata
      },
      local.managed_identity_properties,
    )
  }

  # Write-only: sent on every create and update, and never stored in state or plan files.
  sensitive_body = var.auth_type == "ApiKey" ? {
    properties = {
      credentials = {
        key = ephemeral.azapi_resource_action.subscription_keys[0].output.primaryKey
      }
    }
  } : null

  replace_triggers_external_values = [var.credential_version]

  # Changing connections on the same project in parallel can return an etag conflict.
  retry = {
    error_message_regex = ["TransientError", "Etag conflict"]
  }

  lifecycle {
    # The service stores isSharedToAll = false on a project connection, whatever value is sent; don't keep changing it.
    ignore_changes = [body.properties.isSharedToAll]

    precondition {
      condition     = local.has_model_discovery || local.has_static_models
      error_message = "Set static_models or model_discovery."
    }

    precondition {
      condition     = !(local.has_model_discovery && local.has_static_models)
      error_message = "Set static_models or model_discovery, not both."
    }
  }
}
