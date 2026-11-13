# Foundry agent account (Sub B). This is where developers do all their work.
# `allowProjectManagement = true` because projects are hosted here. No model
# deployments are created on this account — all inference is proxied through
# the APIM gateway to the Foundry model account in Sub A (Foundry alias) or
# to third-party providers (Gemini, Groq aliases).

resource "azapi_resource" "foundry_agent_account" {
  provider  = azapi.development
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_agent_account_name
  location  = coalesce(var.foundry_location, azurerm_resource_group.development.location)
  parent_id = azurerm_resource_group.development.id

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
      customSubDomainName    = local.foundry_agent_account_name
      publicNetworkAccess    = "Enabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }
}
