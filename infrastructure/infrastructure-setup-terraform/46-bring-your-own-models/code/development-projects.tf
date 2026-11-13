# Two governed projects on the Foundry agent account: Alpha and Beta. Each
# project gets its own system-assigned managed identity. That MI's client
# (appid) is what APIM's validate-azure-ad-token policy allowlists — this is
# how Contoso enforces "only these two projects can call the gateway".

resource "azapi_resource" "project_alpha" {
  provider  = azapi.development
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "alpha"
  location  = azapi_resource.foundry_agent_account.location
  parent_id = azapi_resource.foundry_agent_account.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = "Contoso Project Alpha — governed multi-vendor agent development."
      displayName = "Project Alpha"
    }
  }
}

resource "azapi_resource" "project_beta" {
  provider  = azapi.development
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "beta"
  location  = azapi_resource.foundry_agent_account.location
  parent_id = azapi_resource.foundry_agent_account.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = "Contoso Project Beta — governed multi-vendor agent development."
      displayName = "Project Beta"
    }
  }
}

# Note on the APIM allowlist: we gate on the JWT `oid` claim (the SP object
# ID = the project MI's principal_id, already returned by ARM). This avoids
# an Entra Graph lookup, which is useful in tenants where Conditional Access
# blocks Graph token requests for the deploying user.
