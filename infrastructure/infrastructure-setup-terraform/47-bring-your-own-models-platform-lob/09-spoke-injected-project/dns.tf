# Private DNS zones for the BYO agent stores. The hub already owns and links
# the Foundry/APIM zones (cognitiveservices, openai, services.ai,
# azure-api.net) to the spoke VNet via 03-network-registration, so we only
# create the three store zones that do not yet exist, and link them to the
# existing spoke VNet.

resource "azurerm_private_dns_zone" "blob" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = local.spoke_rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "cosmos" {
  name                = "privatelink.documents.azure.com"
  resource_group_name = local.spoke_rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "search" {
  name                = "privatelink.search.windows.net"
  resource_group_name = local.spoke_rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob" {
  name                  = "blob-${local.random_suffix}-link"
  resource_group_name   = local.spoke_rg_name
  private_dns_zone_name = azurerm_private_dns_zone.blob.name
  virtual_network_id    = local.spoke_vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "cosmos" {
  name                  = "cosmos-${local.random_suffix}-link"
  resource_group_name   = local.spoke_rg_name
  private_dns_zone_name = azurerm_private_dns_zone.cosmos.name
  virtual_network_id    = local.spoke_vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "search" {
  name                  = "search-${local.random_suffix}-link"
  resource_group_name   = local.spoke_rg_name
  private_dns_zone_name = azurerm_private_dns_zone.search.name
  virtual_network_id    = local.spoke_vnet_id
  registration_enabled  = false
}

# ---- Private endpoints for the BYO stores, placed in the spoke PE subnet ----

resource "azurerm_private_endpoint" "storage" {
  name                = "pe-${local.storage_name}"
  location            = local.location
  resource_group_name = local.spoke_rg_name
  subnet_id           = local.spoke_pe_snet
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-${local.storage_name}"
    private_connection_resource_id = azurerm_storage_account.agent.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "storage-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }
}

resource "azurerm_private_endpoint" "cosmos" {
  name                = "pe-${local.cosmos_name}"
  location            = local.location
  resource_group_name = local.spoke_rg_name
  subnet_id           = local.spoke_pe_snet
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-${local.cosmos_name}"
    private_connection_resource_id = azurerm_cosmosdb_account.agent.id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "cosmos-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.cosmos.id]
  }
}

resource "azurerm_private_endpoint" "search" {
  name                = "pe-${local.search_name}"
  location            = local.location
  resource_group_name = local.spoke_rg_name
  subnet_id           = local.spoke_pe_snet
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-${local.search_name}"
    private_connection_resource_id = azapi_resource.agent_search.id
    is_manual_connection           = false
    subresource_names              = ["searchService"]
  }

  private_dns_zone_group {
    name                 = "search-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.search.id]
  }
}
