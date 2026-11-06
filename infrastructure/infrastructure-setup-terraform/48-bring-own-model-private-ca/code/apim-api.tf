resource "azurerm_api_management_api" "inference" {
  name                  = "inference"
  resource_group_name   = local.rg_name
  api_management_name   = azurerm_api_management.apim.name
  revision              = "1"
  display_name          = "AI Gateway Inference API"
  path                  = local.apim_api_path
  protocols             = ["https"]
  subscription_required = false

  import {
    content_format = "openapi+json"
    content_value = jsonencode({
      openapi = "3.0.1"
      info = {
        title   = "AI Gateway Inference API"
        version = "1.0"
      }
      paths = {
        "/deployments/{deploymentName}/chat/completions" = {
          post = {
            operationId = "ChatCompletions_Create"
            parameters = [
              {
                name     = "deploymentName"
                in       = "path"
                required = true
                schema   = { type = "string" }
              },
              {
                name     = "api-version"
                in       = "query"
                required = false
                schema   = { type = "string" }
              }
            ]
            requestBody = {
              required = true
              content = {
                "application/json" = { schema = { type = "object" } }
              }
            }
            responses = {
              "200" = {
                description = "Success"
                content = {
                  "application/json" = { schema = { type = "object" } }
                }
              }
            }
          }
        }
      }
    })
  }
}

# Policy: validate the incoming Entra token (pinned to the workload project's
# identity), then forward to the private Foundry model account using APIM's
# managed identity over its outbound VNet integration.
resource "azurerm_api_management_api_policy" "inference" {
  api_name            = azurerm_api_management_api.inference.name
  api_management_name = azurerm_api_management.apim.name
  resource_group_name = local.rg_name

  xml_content = templatefile("${path.module}/apim-policy.xml.tftpl", {
    tenant_id            = local.tenant_id
    token_audience       = local.token_audience
    foundry_endpoint     = local.foundry_model_endpoint
    project_principal_id = azapi_resource.project.identity[0].principal_id
  })

  depends_on = [
    azurerm_role_assignment.apim_cog_user_on_model,
    azurerm_api_management_api.inference,
  ]
}

resource "azurerm_api_management_api_diagnostic" "appi" {
  identifier               = "applicationinsights"
  resource_group_name      = local.rg_name
  api_management_name      = azurerm_api_management.apim.name
  api_name                 = azurerm_api_management_api.inference.name
  api_management_logger_id = azurerm_api_management_logger.appi.id

  sampling_percentage       = 100.0
  always_log_errors         = true
  log_client_ip             = true
  http_correlation_protocol = "W3C"
  verbosity                 = "information"

  frontend_request {
    body_bytes = 0
  }
  frontend_response {
    body_bytes = 0
  }
  backend_request {
    body_bytes = 0
  }
  backend_response {
    body_bytes = 0
  }
}
