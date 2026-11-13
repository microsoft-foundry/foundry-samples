# ============================================================================
# Foundry model backend (platform hub).
#
# Inference-only account: allowProjectManagement = false. It hosts the model
# deployment that the APIM policy forwards to. Public network access is
# disabled; APIM reaches it through its outbound VNet integration and this
# private endpoint in the hub.
# ============================================================================

resource "azapi_resource" "foundry_model_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_model_account_name
  location  = local.create_rg ? azurerm_resource_group.rg[0].location : data.azurerm_resource_group.existing[0].location
  parent_id = local.rg_id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
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

  response_export_values = ["identity.principalId", "properties.endpoint"]
}

resource "azurerm_private_endpoint" "foundry_model" {
  name                = "pe-${local.foundry_model_account_name}"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.hub_pe.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-foundry-model"
    private_connection_resource_id = azapi_resource.foundry_model_account.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "foundry-model-zones"
    private_dns_zone_ids = local.foundry_dns_zone_ids
  }
}

resource "azapi_resource" "foundry_model_deployment" {
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
