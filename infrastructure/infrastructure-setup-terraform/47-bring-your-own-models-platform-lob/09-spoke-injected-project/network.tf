# Delegated Standard-Agent subnet, added to the EXISTING spoke VNet
# (02-spoke-base owns the VNet; this subnet is created here as a separate
# resource, which is safe because 02-spoke-base declares its subnets as
# standalone azurerm_subnet resources — no inline subnet blocks to clobber).
#
# The Microsoft.App/environments delegation is what makes this subnet usable
# as the Foundry Standard-Agent injection target. Injecting the account into
# this subnet is what provisions the agent runtime + data-proxy inside the
# spoke VNet.
resource "azurerm_subnet" "agent" {
  name                 = "snet-agent"
  resource_group_name  = local.spoke_rg_name
  virtual_network_name = local.spoke_vnet_name
  address_prefixes     = [var.agent_subnet_prefix]

  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

resource "azurerm_route_table" "agent" {
  name                = "rt-${var.name_prefix}-agent-${local.random_suffix}"
  location            = local.location
  resource_group_name = local.spoke_rg_name
  tags                = local.common_tags

  route {
    name                   = "default-via-hub-firewall"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = data.terraform_remote_state.hub_base.outputs.hub_firewall_private_ip
  }
}

resource "azurerm_subnet_route_table_association" "agent" {
  subnet_id      = azurerm_subnet.agent.id
  route_table_id = azurerm_route_table.agent.id
}
