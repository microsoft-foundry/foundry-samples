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
