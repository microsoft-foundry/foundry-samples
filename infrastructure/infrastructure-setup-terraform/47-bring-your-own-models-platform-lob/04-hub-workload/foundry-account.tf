# Foundry model account — inference-only backend. Public network access is
# disabled per H3; the account is reachable only via a private endpoint
# in snet-pe. Local auth is disabled per H4 so APIM authenticates as its
# system-assigned MI.

data "azurerm_resource_group" "hub" {
  name = local.hub_rg_name
}

resource "azapi_resource" "foundry_model_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_model_account_name
  location  = data.azurerm_resource_group.hub.location
  parent_id = local.hub_rg_id

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
      publicNetworkAccess    = "Disabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Deny"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }

  response_export_values = ["identity", "properties.endpoint"]

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Private endpoint for the Foundry model account (OpenAI plane).
# The privatelink.openai.azure.com and privatelink.cognitiveservices.azure.com
# zones are linked to both hub and spoke VNets so callers on either plane
# resolve the same private IP.
# ---------------------------------------------------------------------------
resource "azurerm_private_endpoint" "foundry_model" {
  name                = "pe-${local.foundry_model_account_name}"
  location            = local.location
  resource_group_name = local.hub_rg_name
  subnet_id           = local.private_endpoint_subnet_id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-foundry-model"
    private_connection_resource_id = azapi_resource.foundry_model_account.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name = "foundry-model-zones"
    private_dns_zone_ids = [
      local.private_dns_zone_ids["privatelink.openai.azure.com"],
      local.private_dns_zone_ids["privatelink.cognitiveservices.azure.com"],
      local.private_dns_zone_ids["privatelink.services.ai.azure.com"],
    ]
  }
}
