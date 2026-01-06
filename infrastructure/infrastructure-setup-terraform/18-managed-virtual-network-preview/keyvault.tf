# Generate a random password for VM admin
resource "random_password" "vm_admin" {
  count            = var.enable_vm ? 1 : 0
  length           = 24
  special          = true
  override_special = "!@#$%^&*()-_=+[]{}:?"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

# Key Vault
resource "azurerm_key_vault" "main" {
  count                      = var.enable_vm ? 1 : 0
  name                       = local.keyvault_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # Enable public network access with network rules to allow specific IPs
  public_network_access_enabled = length(var.allowed_public_ips) > 0 ? true : false

  # Network ACLs to restrict access
  network_acls {
    bypass         = "AzureServices"
    default_action = length(var.allowed_public_ips) > 0 ? "Deny" : "Allow"
    ip_rules       = var.allowed_public_ips
  }

  # Enable RBAC for access control
  rbac_authorization_enabled = true

  tags = {
    environment = "lab"
  }
}

# Private Endpoint for Key Vault
resource "azurerm_private_endpoint" "keyvault" {
  count               = var.enable_vm && var.enable_networking ? 1 : 0
  name                = "${azurerm_key_vault.main[0].name}-pe"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints[0].id

  private_service_connection {
    name                           = "${azurerm_key_vault.main[0].name}-psc"
    private_connection_resource_id = azurerm_key_vault.main[0].id
    is_manual_connection           = false
    subresource_names              = ["vault"]
  }

  private_dns_zone_group {
    name                 = "keyvault-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.key_vault[0].id]
  }

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Role Assignment: Key Vault Administrator for current user
resource "azurerm_role_assignment" "current_user_keyvault_admin" {
  count                = var.enable_vm ? 1 : 0
  scope                = azurerm_key_vault.main[0].id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role Assignment: Key Vault Secrets User for VM managed identity
# This allows the VM to read secrets (useful for future automation scenarios)
resource "azurerm_role_assignment" "vm_keyvault_secrets_user" {
  count                = var.enable_vm ? 1 : 0
  scope                = azurerm_key_vault.main[0].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_windows_virtual_machine.main[0].identity[0].principal_id
}

# Wait for RBAC propagation for Key Vault
resource "time_sleep" "wait_keyvault_rbac" {
  count           = var.enable_vm ? 1 : 0
  create_duration = "30s"

  depends_on = [
    azurerm_role_assignment.current_user_keyvault_admin
  ]
}

# Store VM admin password in Key Vault
resource "azurerm_key_vault_secret" "vm_admin_password" {
  count        = var.enable_vm ? 1 : 0
  name         = "vm-admin-password"
  value        = random_password.vm_admin[0].result
  key_vault_id = azurerm_key_vault.main[0].id

  depends_on = [
    time_sleep.wait_keyvault_rbac
  ]

  tags = merge(
    var.tags,
    {
      environment = "lab"
      purpose     = "VM administrator password"
    }
  )
}

# Store VM admin username in Key Vault for reference
resource "azurerm_key_vault_secret" "vm_admin_username" {
  count        = var.enable_vm ? 1 : 0
  name         = "vm-admin-username"
  value        = var.vm_admin_username
  key_vault_id = azurerm_key_vault.main[0].id

  depends_on = [
    time_sleep.wait_keyvault_rbac
  ]

  tags = merge(
    var.tags,
    {
      environment = "lab"
      purpose     = "VM administrator username"
    }
  )
}
