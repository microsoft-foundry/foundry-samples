# Storage Account
resource "azurerm_storage_account" "main" {
  count                    = var.enable_storage ? 1 : 0
  name                     = local.storage_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  shared_access_key_enabled = false
  allow_nested_items_to_be_public = false

  # Disable public network access - only accessible via private endpoints
  public_network_access_enabled = false

  # Ignore changes to queue/blob/file/table properties to avoid validation issues
  lifecycle {
    ignore_changes = [
      queue_properties,
      blob_properties,
      share_properties
    ]
  }

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Private Endpoint for Blob
resource "azurerm_private_endpoint" "storage_blob" {
  count               = var.enable_storage && var.enable_networking ? 1 : 0
  name                = "${azurerm_storage_account.main[0].name}-blob-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_storage_account.main[0].name}-blob-psc"
    private_connection_resource_id = azurerm_storage_account.main[0].id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "blob-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.storage_blob[0].id]
  }
}

# Private Endpoint for File
resource "azurerm_private_endpoint" "storage_file" {
  count               = var.enable_storage && var.enable_networking ? 1 : 0
  name                = "${azurerm_storage_account.main[0].name}-file-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_storage_account.main[0].name}-file-psc"
    private_connection_resource_id = azurerm_storage_account.main[0].id
    is_manual_connection           = false
    subresource_names              = ["file"]
  }

  private_dns_zone_group {
    name                 = "file-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.storage_file[0].id]
  }
}

# Private Endpoint for Table
resource "azurerm_private_endpoint" "storage_table" {
  count               = var.enable_storage && var.enable_networking ? 1 : 0
  name                = "${azurerm_storage_account.main[0].name}-table-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_storage_account.main[0].name}-table-psc"
    private_connection_resource_id = azurerm_storage_account.main[0].id
    is_manual_connection           = false
    subresource_names              = ["table"]
  }

  private_dns_zone_group {
    name                 = "table-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.storage_table[0].id]
  }
}

# Private Endpoint for Queue
resource "azurerm_private_endpoint" "storage_queue" {
  count               = var.enable_storage && var.enable_networking ? 1 : 0
  name                = "${azurerm_storage_account.main[0].name}-queue-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_storage_account.main[0].name}-queue-psc"
    private_connection_resource_id = azurerm_storage_account.main[0].id
    is_manual_connection           = false
    subresource_names              = ["queue"]
  }

  private_dns_zone_group {
    name                 = "queue-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.storage_queue[0].id]
  }
}

# Role Assignment: Current user needs Storage Blob Data Contributor for Terraform to manage storage
resource "azurerm_role_assignment" "current_user_storage_blob" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role Assignment: Current user needs Storage Queue Data Contributor
resource "azurerm_role_assignment" "current_user_storage_queue" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role Assignment: Current user needs Storage File Data SMB Share Contributor
resource "azurerm_role_assignment" "current_user_storage_file" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage File Data SMB Share Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role Assignment: Current user needs Storage Table Data Contributor
resource "azurerm_role_assignment" "current_user_storage_table" {
  count                = var.enable_storage ? 1 : 0
  scope                = azurerm_storage_account.main[0].id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}
