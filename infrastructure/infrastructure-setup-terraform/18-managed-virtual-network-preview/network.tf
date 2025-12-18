# Virtual Network
resource "azurerm_virtual_network" "main" {
  count               = var.enable_networking ? 1 : 0
  name                = var.vnet_name
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_address_prefix]
}

# Subnets
resource "azurerm_subnet" "private_endpoints" {
  count                             = var.enable_networking ? 1 : 0
  name                              = var.private_endpoints_subnet_name
  resource_group_name               = azurerm_resource_group.main.name
  virtual_network_name              = azurerm_virtual_network.main[0].name
  address_prefixes                  = [var.private_endpoints_subnet_prefix]
  default_outbound_access_enabled   = true
}
