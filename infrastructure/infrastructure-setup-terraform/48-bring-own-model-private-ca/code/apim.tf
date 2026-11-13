# ============================================================================
# APIM gateway (Standard v2, platform hub) fronting the Foundry model.
#
# * Inbound:  private endpoint in the hub. Application Gateway forwards to
#             APIM's default *.azure-api.net hostname, which resolves to this
#             endpoint through the hub-linked privatelink.azure-api.net zone.
# * Outbound: VNet integration (delegated hub subnet) so APIM reaches the
#             private model endpoint.
#
# APIM deliberately has NO custom domain: APIM validates custom hostname
# ownership against publicly resolvable DNS, which an internal-only name cannot
# satisfy (CustomHostnameOwnershipCheckFailed). Application Gateway serves the
# private-CA certificate on the internal gateway hostname instead.
# ============================================================================

resource "azurerm_api_management" "apim" {
  name                          = local.apim_name
  location                      = var.location
  resource_group_name           = local.rg_name
  publisher_name                = var.apim_publisher_name
  publisher_email               = var.apim_publisher_email
  sku_name                      = var.apim_sku
  public_network_access_enabled = var.apim_public_network_access_enabled

  virtual_network_type = "External"
  virtual_network_configuration {
    subnet_id = azurerm_subnet.apim_integration.id
  }

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags

  depends_on = [azurerm_subnet_network_security_group_association.apim_integration]
}

# ---- APIM can call the Foundry model account (backend, AAD auth) ----
resource "azurerm_role_assignment" "apim_cog_user_on_model" {
  scope                = azapi_resource.foundry_model_account.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_api_management.apim.identity[0].principal_id
}

# ---- Private endpoint for APIM's gateway, in the hub PE subnet ----
resource "azurerm_private_endpoint" "apim" {
  name                = "pe-${local.apim_name}"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.hub_pe.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-apim"
    private_connection_resource_id = azurerm_api_management.apim.id
    is_manual_connection           = false
    subresource_names              = ["Gateway"]
  }

  private_dns_zone_group {
    name                 = "apim-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.apim.id]
  }
}

# ---- APIM -> Application Insights logger ----
resource "azurerm_api_management_logger" "appi" {
  name                = "appi-logger"
  api_management_name = azurerm_api_management.apim.name
  resource_group_name = local.rg_name
  resource_id         = azurerm_application_insights.appi.id

  application_insights {
    connection_string = azurerm_application_insights.appi.connection_string
  }
}
