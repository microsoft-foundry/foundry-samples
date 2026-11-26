# ============================================================================
# ModelGateway connection on a Foundry project.
#
# Terraform version of
# infrastructure-setup-bicep/01-connections/model-gateway/connection-modelgateway.bicep:
# the same inputs produce the same connection. The metadata includes only the
# settings you set, and its nested values are JSON strings.
# ============================================================================

locals {
  connection_name     = var.connection_name != "" ? var.connection_name : "modelgateway-${var.gateway_name}-comprehensive"
  has_model_discovery = var.model_discovery != null
  has_static_models   = length(var.static_models) > 0

  metadata = merge(
    {
      deploymentInPath    = tostring(var.deployment_in_path)
      inferenceAPIVersion = var.inference_api_version
    },
    var.upstream_surface != "" ? { upstreamSurface = var.upstream_surface } : {},
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

  # OAuth2 connections also carry the token endpoint and scopes.
  oauth2_properties = { for k, v in { tokenUrl = var.token_url, scopes = var.scopes } : k => v if var.auth_type == "OAuth2" }
}

resource "azapi_resource" "connection" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = local.connection_name
  parent_id                 = var.project_resource_id
  schema_validation_enabled = false

  body = {
    properties = merge(
      {
        category      = "ModelGateway"
        target        = var.target_url
        authType      = var.auth_type
        isSharedToAll = var.is_shared_to_all
        metadata      = local.metadata
      },
      local.oauth2_properties,
    )
  }

  # Write-only: sent on every create and update, and never stored in state or plan files.
  sensitive_body = {
    properties = {
      credentials = var.auth_type == "ApiKey" ? { key = var.api_key } : { clientId = var.client_id, clientSecret = var.client_secret }
    }
  }

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

    precondition {
      condition     = var.auth_type != "OAuth2" || (var.client_id != "" && var.token_url != "")
      error_message = "client_id and token_url are required when auth_type is OAuth2."
    }
  }
}
