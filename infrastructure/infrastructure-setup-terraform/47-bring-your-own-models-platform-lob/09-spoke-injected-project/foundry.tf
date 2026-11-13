# Injected Foundry agent account. Identical private posture to sample 47's
# 05-spoke-workload-project account (PNA disabled, deny ACLs, local auth off)
# BUT with the critical addition of `networkInjections` -> the delegated
# agent subnet. THIS is what makes the account provision the agent runtime +
# data-proxy inside the spoke VNet, so the projects-scoped Responses -> APIM
# (BYOG) path flows through the data-proxy.
#
# networkInjections is create-time only, which is why this is a NEW account
# rather than a retrofit of the existing sample-47 account.
resource "azapi_resource" "foundry_agent_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_agent_account_name
  location  = local.location
  parent_id = local.spoke_rg_id
  tags      = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.foundry_agent_account_name
      publicNetworkAccess    = "Disabled"
      disableLocalAuth       = true
      networkAcls = {
        defaultAction       = "Deny"
        virtualNetworkRules = []
        ipRules             = []
      }

      # VNet injection for Standard Agents -> provisions the data-proxy.
      networkInjections = [
        {
          scenario                   = "agent"
          subnetArmId                = azurerm_subnet.agent.id
          useMicrosoftManagedNetwork = false
        }
      ]
    }
  }

  response_export_values = ["identity.principalId"]

  depends_on = [azurerm_subnet.agent]
}

# Private endpoint for the injected account. DNS resolves through the
# hub-owned zones that 03-network-registration already linked to the spoke
# VNet (cross-subscription zone IDs).
resource "azurerm_private_endpoint" "foundry_agent" {
  name                = "pe-${local.foundry_agent_account_name}"
  location            = local.location
  resource_group_name = local.spoke_rg_name
  subnet_id           = local.spoke_pe_snet
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-foundry-agent"
    private_connection_resource_id = azapi_resource.foundry_agent_account.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "foundry-account-zones"
    private_dns_zone_ids = local.foundry_dns_zone_ids
  }
}

# NOTE: Unlike the non-injected sample-47 account (05-spoke-workload-project),
# a VNet-injected account must NOT have a manually-created account-level
# capability host. For injected accounts the platform manages the account
# caphost (a manual PUT fails with "customerSubnet must match the subnet
# recorded on the Foundry account"). Sample 15a — the canonical injected
# setup — creates only the project-level caphost (see project.tf). The
# project caphost below drives account caphost provisioning implicitly.
