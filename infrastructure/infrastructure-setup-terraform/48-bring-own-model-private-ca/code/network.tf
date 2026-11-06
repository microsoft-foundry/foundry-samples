# ============================================================================
# Hub-and-spoke networking (single subscription, bidirectional peering).
#
# Workload spoke:
#   * snet-agent  - delegated to Microsoft.App/environments. Injecting the
#                   Foundry agent account here provisions the agent runtime and
#                   the single-tenant data proxy, which calls the hub gateway.
#   * snet-pe     - spoke private endpoints (Foundry account, Storage, Cosmos,
#                   Search).
#
# Platform hub:
#   * snet-appgw  - Application Gateway; its private frontend serves the
#                   private-CA certificate on the gateway hostname.
#   * snet-pe     - hub private endpoints (APIM gateway, Foundry model account).
#   * snet-apim   - APIM Standard v2 outbound VNet integration (delegated to
#                   Microsoft.Web/serverFarms) so APIM reaches the private model.
# ============================================================================

# ---- Workload spoke ----
resource "azurerm_virtual_network" "spoke" {
  name                = local.spoke_vnet_name
  location            = var.location
  resource_group_name = local.rg_name
  address_space       = [var.spoke_vnet_address_space]
  tags                = local.common_tags
}

moved {
  from = azurerm_virtual_network.vnet
  to   = azurerm_virtual_network.spoke
}

resource "azurerm_subnet" "agent" {
  name                 = "snet-agent"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.agent_subnet_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "spoke_pe" {
  name                 = "snet-pe"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_pe_subnet_prefix]
}

moved {
  from = azurerm_subnet.pe
  to   = azurerm_subnet.spoke_pe
}

# ---- Platform hub ----
resource "azurerm_virtual_network" "hub" {
  name                = local.hub_vnet_name
  location            = var.location
  resource_group_name = local.rg_name
  address_space       = [var.hub_vnet_address_space]
  tags                = local.common_tags
}

resource "azurerm_subnet" "hub_pe" {
  name                 = "snet-pe"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_pe_subnet_prefix]
}

resource "azurerm_subnet" "appgw" {
  name                 = "snet-appgw"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.appgw_subnet_prefix]
}

resource "azurerm_subnet" "apim_integration" {
  name                 = "snet-apim"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.apim_integration_subnet_prefix]

  delegation {
    name = "Microsoft.Web/serverFarms"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# APIM v2 VNet integration requires an NSG on the subnet, with outbound access
# to Azure Key Vault.
resource "azurerm_network_security_group" "apim_integration" {
  name                = "nsg-${local.apim_name}"
  location            = var.location
  resource_group_name = local.rg_name
  tags                = local.common_tags

  security_rule {
    name                       = "AllowKeyVaultOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "AzureKeyVault"
  }
}

resource "azurerm_subnet_network_security_group_association" "apim_integration" {
  subnet_id                 = azurerm_subnet.apim_integration.id
  network_security_group_id = azurerm_network_security_group.apim_integration.id
}

# ---- Hub <-> spoke peering ----
resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                      = "peer-spoke-to-hub"
  resource_group_name       = local.rg_name
  virtual_network_name      = azurerm_virtual_network.spoke.name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
}

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                      = "peer-hub-to-spoke"
  resource_group_name       = local.rg_name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.spoke.id
}
