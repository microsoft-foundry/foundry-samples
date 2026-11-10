# ============================================================================
# BYO agent stores required by the project-level capability host.
#
# A VNet-injected Agents capability host requires customer-owned Storage
# (blob), Cosmos DB (thread storage), and AI Search (vector store). All three
# are private-endpoint-only and AAD-authenticated, consistent with the private
# posture of samples 15a / 47-09.
# ============================================================================

resource "azurerm_storage_account" "agent" {
  name                          = local.storage_name
  resource_group_name           = local.rg_name
  location                      = var.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  public_network_access_enabled = false
  shared_access_key_enabled     = false
  tags                          = local.common_tags
}

resource "azurerm_cosmosdb_account" "agent" {
  name                          = local.cosmos_name
  location                      = var.location
  resource_group_name           = local.rg_name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = false
  tags                          = local.common_tags

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }
}

resource "azurerm_search_service" "agent" {
  name                          = local.search_name
  resource_group_name           = local.rg_name
  location                      = var.location
  sku                           = "standard"
  local_authentication_enabled  = false
  public_network_access_enabled = false
  tags                          = local.common_tags
}

# ---- Private endpoints for the stores ----
resource "azurerm_private_endpoint" "storage" {
  name                = "pe-${local.storage_name}"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.spoke_pe.id
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
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.spoke_pe.id
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
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.spoke_pe.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-${local.search_name}"
    private_connection_resource_id = azurerm_search_service.agent.id
    is_manual_connection           = false
    subresource_names              = ["searchService"]
  }

  private_dns_zone_group {
    name                 = "search-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.search.id]
  }
}
