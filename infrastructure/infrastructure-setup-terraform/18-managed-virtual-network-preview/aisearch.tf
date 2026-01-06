# AI Search Service
resource "azurerm_search_service" "main" {
  count               = var.enable_aisearch ? 1 : 0
  name                = local.aisearch_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "standard"
  replica_count       = 1
  partition_count     = 1

  public_network_access_enabled = true
  
  identity {
    type = "SystemAssigned"
  }

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Private Endpoint for AI Search
resource "azurerm_private_endpoint" "aisearch" {
  count               = var.enable_aisearch && var.enable_networking ? 1 : 0
  name                = "${azurerm_search_service.main[0].name}-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_search_service.main[0].name}-psc"
    private_connection_resource_id = azurerm_search_service.main[0].id
    is_manual_connection           = false
    subresource_names              = ["searchService"]
  }

  private_dns_zone_group {
    name                 = "aisearch-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.aisearch[0].id]
  }

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Wait for AI Search to be fully created before creating outbound rule

# Wait for AI Search to be fully created before creating outbound rule
resource "time_sleep" "wait_aisearch" {
  count           = var.enable_aisearch ? 1 : 0
  create_duration = "10m"

  depends_on = [
    azurerm_search_service.main,
    azurerm_private_endpoint.aisearch
  ]
}

# Managed Network Outbound Rule for AI Search Service
resource "azapi_resource" "aisearch_outbound_rule" {
  count     = var.enable_aisearch ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/managedNetworks/outboundRules@2025-10-01-preview"
  name      = "aisearch-rule"
  parent_id = azapi_resource.managed_network.id

  schema_validation_enabled = false

  body = {
    properties = {
      type = "PrivateEndpoint"
      destination = {
        serviceResourceId = azurerm_search_service.main[0].id
        subresourceTarget = "searchService"
      }
      category = "UserDefined"
    }
  }

  depends_on = [
    time_sleep.wait_aisearch,
    azurerm_role_assignment.foundry_network_connection_approver,
    azurerm_role_assignment.project_search_index,
    azurerm_role_assignment.project_search_contributor
  ]
}

# Role Assignment: Current user needs Search Service Contributor
resource "azurerm_role_assignment" "current_user_search_contributor" {
  count                = var.enable_aisearch ? 1 : 0
  scope                = azurerm_search_service.main[0].id
  role_definition_name = "Search Service Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role Assignment: Current user needs Search Index Data Contributor
resource "azurerm_role_assignment" "current_user_search_index" {
  count                = var.enable_aisearch ? 1 : 0
  scope                = azurerm_search_service.main[0].id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

