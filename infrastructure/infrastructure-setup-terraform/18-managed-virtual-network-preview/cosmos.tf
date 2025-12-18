# Cosmos DB Account
resource "azurerm_cosmosdb_account" "main" {
  count               = var.enable_cosmos ? 1 : 0
  name                = local.cosmos_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level       = "Session"
    max_interval_in_seconds = 5
    max_staleness_prefix    = 100
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  public_network_access_enabled = false
  network_acl_bypass_for_azure_services = false
  local_authentication_disabled = true

  tags = {
    environment = "lab"
  }
}

# Private Endpoint for Cosmos DB
resource "azurerm_private_endpoint" "cosmos" {
  count               = var.enable_cosmos && var.enable_networking ? 1 : 0
  name                = "${azurerm_cosmosdb_account.main[0].name}-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_cosmosdb_account.main[0].name}-psc"
    private_connection_resource_id = azurerm_cosmosdb_account.main[0].id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "cosmos-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.cosmos[0].id]
  }

  tags = {
    environment = "lab"
  }
}

# Role Assignment: Current user needs Cosmos DB Built-in Data Contributor
resource "azurerm_cosmosdb_sql_role_assignment" "current_user" {
  count               = var.enable_cosmos ? 1 : 0
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main[0].name
  role_definition_id  = "${azurerm_cosmosdb_account.main[0].id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = data.azurerm_client_config.current.object_id
  scope               = azurerm_cosmosdb_account.main[0].id
}
