# One governed Foundry project. Its system-assigned managed identity is the
# principal that the APIM gateway allowlists. principal_id (= objectId in
# Entra) is what the JWT `oid` claim carries, so the platform team pastes
# `output.project_managed_identity_object_id` into
# hub-allowlist/allowlist.auto.tfvars via PR (step 4).

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  location  = azapi_resource.foundry_agent_account.location
  parent_id = azapi_resource.foundry_agent_account.id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = var.project_description
      displayName = var.project_display_name
    }
  }

  response_export_values = ["identity.principalId"]
}
