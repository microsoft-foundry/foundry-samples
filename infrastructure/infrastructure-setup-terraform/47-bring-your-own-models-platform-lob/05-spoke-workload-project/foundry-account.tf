# Foundry agent account. Private-network posture matches sample 47:
#   * publicNetworkAccess = Disabled
#   * networkAcls.defaultAction = Deny
#   * disableLocalAuth = true
#   * allowProjectManagement = true (this is the account that hosts projects)
#
# No model deployments are created on this account. All inference is proxied
# through the platform APIM gateway to either the Foundry model account in
# the hub or to third-party providers.

data "azurerm_resource_group" "spoke" {
  name = local.spoke_rg_name
}

resource "azapi_resource" "foundry_agent_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_agent_account_name
  location  = data.azurerm_resource_group.spoke.location
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
    }
  }

  response_export_values = ["identity.principalId"]
}

# Private endpoint in the spoke PE subnet. DNS resolution flows through the
# hub-owned zones that network-registration linked to the spoke VNet.
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

  # The three Foundry zones live in the hub subscription. VNet linking
  # only enables *lookups* on the zone — it does NOT populate records.
  # A DNS zone group on the PE is what makes Azure auto-register the
  # `<account>` A record in each linked zone. Cross-subscription zone IDs
  # are supported here.
  private_dns_zone_group {
    name                 = "foundry-account-zones"
    private_dns_zone_ids = local.foundry_dns_zone_ids
  }
}
