# ============================================================================
# "Admin-connected models" connection from a Foundry project to an AI Gateway.
#
# category ModelGateway + ApiKey: a prompt agent references the gateway model as
# <connection_name>/<model_name> and calls it through the Responses API.
# deploymentInPath "false" puts the model name in the request body, matching the
# gateway's /openai/v1 endpoint.
# ============================================================================

locals {
  account_name = split("/", var.project_id)[8]
  project_name = split("/", var.project_id)[10]

  # Static model list: lets the runtime resolve <connection>/<model> without a
  # discovery call, and lets the portal render the model.
  static_models = [
    {
      name = var.model_name
      properties = {
        model = {
          name    = var.model_name
          version = var.model_version
          format  = var.model_format
        }
      }
    }
  ]
}

resource "azapi_resource" "connection" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = var.connection_name
  parent_id                 = var.project_id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "ModelGateway"
      target        = var.base_url
      authType      = "ApiKey"
      isSharedToAll = var.is_shared_to_all
      metadata = {
        models           = jsonencode(local.static_models)
        deploymentInPath = "false"
        authHeaderName   = var.auth_header_name
        authHeaderFormat = var.auth_header_format
        customHeaders    = "{}"
      }
    }
  }

  # Write-only: sent on every create/update, never stored in state.
  sensitive_body = {
    properties = {
      credentials = {
        key = var.api_key
      }
    }
  }

  replace_triggers_external_values = [var.credential_version]

  # Connections on the same project can conflict when changed in parallel (etag).
  retry = {
    error_message_regex = ["TransientError", "Etag conflict"]
  }

  # Project-scoped connections report isSharedToAll = false on read even when
  # true is sent; ignore it so plans don't show perpetual drift.
  lifecycle {
    ignore_changes = [body.properties.isSharedToAll]
  }
}
