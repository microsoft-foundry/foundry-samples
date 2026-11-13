# Foundry model account (Sub A). This is an inference-only backend — it hosts
# the gpt-4o model deployment that APIM proxies to. Because agents and
# projects run in Sub B, `allowProjectManagement` is set to false here.
resource "azapi_resource" "foundry_model_account" {
  provider  = azapi.platform
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_model_account_name
  location  = coalesce(var.foundry_location, azurerm_resource_group.platform.location)
  parent_id = azurerm_resource_group.platform.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = false
      customSubDomainName    = local.foundry_model_account_name
      publicNetworkAccess    = "Enabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }

  response_export_values = ["identity", "properties.endpoint"]
}

# Model deployment on the Foundry model account. Its name (e.g. `gpt-4o`) is
# the deployment segment that Foundry SDK includes in the URL. APIM matches
# on that name and forwards to this account when the alias belongs to the
# Foundry vendor branch of the policy.
resource "azapi_resource" "foundry_gpt4o_deployment" {
  provider  = azapi.platform
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.foundry_model_name
  parent_id = azapi_resource.foundry_model_account.id

  body = {
    sku = {
      name     = "GlobalStandard"
      capacity = var.foundry_model_capacity
    }
    properties = {
      model = {
        name    = var.foundry_model_name
        format  = "OpenAI"
        version = var.foundry_model_version
      }
    }
  }
}
