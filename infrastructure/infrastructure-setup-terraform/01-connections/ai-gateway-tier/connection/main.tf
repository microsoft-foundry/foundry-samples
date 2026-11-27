# ============================================================================
# Spoke connection: attach an EXISTING Foundry project to the hub AI Gateway.
#
# Reads the gateway's runtime host name and API key directly from the hub (the
# key is ephemeral: never written to state or plan), then creates a ModelGateway
# "Admin-connected models" connection on the project. Run once per spoke project.
# ============================================================================

data "azapi_resource" "gateway" {
  type                   = "Microsoft.ApiManagement/aigateways@2025-09-01-preview"
  resource_id            = var.gateway_id
  response_export_values = ["properties.frontend.defaultHostname"]
}

ephemeral "azapi_resource_action" "gateway_key" {
  type                   = "Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview"
  resource_id            = "${var.gateway_id}/apiKeys/${var.api_key_name}"
  action                 = "listSecrets"
  method                 = "POST"
  response_export_values = ["primaryKey"]
}

module "connection" {
  source = "../modules/ai-gateway-connection"

  project_id         = var.project_resource_id
  connection_name    = var.connection_name
  base_url           = "https://${data.azapi_resource.gateway.output.properties.frontend.defaultHostname}/default/models/openai/v1"
  api_key            = ephemeral.azapi_resource_action.gateway_key.output.primaryKey
  credential_version = var.credential_version
  model_name         = var.model_name
  model_version      = var.model_version
  is_shared_to_all   = var.is_shared_to_all
  auth_header_name   = var.auth_header_name
  auth_header_format = var.auth_header_format
}
