## Private DNS zones linked to the VNet, and private endpoints for the agent's
## Foundry account and data stores. Created one at a time to avoid concurrent
## writes to the same VNet/subnet.
##
locals {
  private_dns_zones = {
    cosmos_db          = "privatelink.documents.azure.com"
    ai_search          = "privatelink.search.windows.net"
    storage_blob       = "privatelink.blob.core.windows.net"
    cognitive_services = "privatelink.cognitiveservices.azure.com"
    ai_services        = "privatelink.services.ai.azure.com"
    openai             = "privatelink.openai.azure.com"
  }
}

resource "azurerm_private_dns_zone" "zones" {
  for_each            = local.private_dns_zones
  name                = each.value
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "links" {
  for_each              = local.private_dns_zones
  name                  = "${each.key}-${local.suffix}-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.zones[each.key].name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  registration_enabled  = false
}

locals {
  foundry_dns_zone_ids = [
    azurerm_private_dns_zone.zones["cognitive_services"].id,
    azurerm_private_dns_zone.zones["ai_services"].id,
    azurerm_private_dns_zone.zones["openai"].id,
  ]
}

resource "azurerm_private_endpoint" "storage" {
  name                = "${azurerm_storage_account.storage.name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "${azurerm_storage_account.storage.name}-psc"
    private_connection_resource_id = azurerm_storage_account.storage.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["storage_blob"].id]
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.links]
}

resource "azurerm_private_endpoint" "cosmosdb" {
  name                = "${azurerm_cosmosdb_account.cosmosdb.name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "${azurerm_cosmosdb_account.cosmosdb.name}-psc"
    private_connection_resource_id = azurerm_cosmosdb_account.cosmosdb.id
    subresource_names              = ["Sql"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["cosmos_db"].id]
  }

  depends_on = [azurerm_private_endpoint.storage]
}

resource "azurerm_private_endpoint" "ai_search" {
  name                = "${azapi_resource.ai_search.name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "${azapi_resource.ai_search.name}-psc"
    private_connection_resource_id = azapi_resource.ai_search.id
    subresource_names              = ["searchService"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["ai_search"].id]
  }

  depends_on = [azurerm_private_endpoint.cosmosdb]
}

resource "azurerm_private_endpoint" "foundry" {
  name                = "${azapi_resource.foundry.name}-pe"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "${azapi_resource.foundry.name}-psc"
    private_connection_resource_id = azapi_resource.foundry.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = local.foundry_dns_zone_ids
  }

  depends_on = [azurerm_private_endpoint.ai_search]
}
