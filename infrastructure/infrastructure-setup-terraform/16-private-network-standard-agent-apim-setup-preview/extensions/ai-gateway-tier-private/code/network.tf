## Virtual network with the agent subnet and the private-endpoint subnet.
## The gateway's own subnet is in gateway.tf.
##
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-${var.name_prefix}-${local.suffix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.virtual_network_address_space]
}

resource "azurerm_subnet" "agent" {
  name                 = "snet-agent"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.agent_subnet_address_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-pe"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.private_endpoint_subnet_address_prefix]
}
