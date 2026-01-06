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

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
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

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Role Assignment: AI Foundry Account Identity - Contributor on Cosmos DB
resource "azurerm_role_assignment" "foundry_cosmos_contributor" {
  count                = var.enable_cosmos ? 1 : 0
  scope                = azurerm_cosmosdb_account.main[0].id
  role_definition_name = "Contributor"
  principal_id         = azapi_resource.cognitive_account.identity[0].principal_id
}

# Wait for Cosmos DB to be fully created before creating outbound rule
resource "time_sleep" "wait_cosmos" {
  count           = var.enable_cosmos ? 1 : 0
  create_duration = "10m"

  depends_on = [
    azurerm_cosmosdb_account.main,
    azurerm_private_endpoint.cosmos
  ]
}

# Managed Network Outbound Rule for Cosmos DB Account
resource "azapi_resource" "cosmos_outbound_rule" {
  count     = var.enable_cosmos ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules@2025-10-01-preview"
  name      = "cosmos-sql-rule"
  parent_id = azapi_resource.managed_network.id

  schema_validation_enabled = false

  body = {
    properties = {
      type = "PrivateEndpoint"
      destination = {
        serviceResourceId = azurerm_cosmosdb_account.main[0].id
        subresourceTarget = "Sql"
      }
      category = "UserDefined"
    }
  }

  depends_on = [
    time_sleep.wait_cosmos,
    azurerm_role_assignment.foundry_network_connection_approver,
    azurerm_role_assignment.foundry_cosmos_contributor,
    azurerm_role_assignment.project_cosmos_reader,
    azurerm_role_assignment.project_cosmos_operator
  ]
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
