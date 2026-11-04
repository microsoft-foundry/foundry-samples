# ============================================================================
# VNet-injected Foundry agent account (workload spoke).
#
# networkInjections -> the delegated spoke agent subnet provisions the agent
# runtime and the SINGLE-TENANT DATA PROXY inside the spoke. The data proxy
# calls the hub gateway over peering and validates its private-CA certificate.
#
# properties.trustedCertificateSources registers the private root CA from the
# start. The trust bundle is loaded into the data proxy when the capability
# host is created (project.tf), after the account identity can read the secret.
# ============================================================================

locals {
  # Public access only affects how clients reach the account. Network injection
  # keeps the data proxy in the spoke, so the gateway path stays private.
  foundry_public_access_enabled = var.foundry_public_network_access_enabled || length(var.foundry_allowed_ip_ranges) > 0

  agent_account_properties = {
    allowProjectManagement = true
    customSubDomainName    = local.foundry_agent_account_name
    publicNetworkAccess    = local.foundry_public_access_enabled ? "Enabled" : "Disabled"
    disableLocalAuth       = true
    networkAcls = {
      defaultAction       = var.foundry_public_network_access_enabled && length(var.foundry_allowed_ip_ranges) == 0 ? "Allow" : "Deny"
      virtualNetworkRules = []
      ipRules             = [for rule in local.foundry_allowed_ip_rules : { value = rule }]
    }
    networkInjections = [
      {
        scenario                   = "agent"
        subnetArmId                = azurerm_subnet.agent.id
        useMicrosoftManagedNetwork = false
      }
    ]
    trustedCertificateSources = local.trusted_certificate_sources
  }
}

resource "azapi_resource" "foundry_agent_account" {
  type      = "Microsoft.CognitiveServices/accounts@2026-11-15-preview"
  name      = local.foundry_agent_account_name
  location  = var.location
  parent_id = local.rg_id
  tags      = local.common_tags

  # trustedCertificateSources is a public-preview property that may not be in
  # the azapi embedded schema; skip client-side validation.
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind       = "AIServices"
    sku        = { name = "S0" }
    properties = local.agent_account_properties
  }

  response_export_values = ["identity.principalId"]

  depends_on = [azurerm_subnet.agent]
}

# Private endpoint for the injected account.
resource "azurerm_private_endpoint" "foundry_agent" {
  name                = "pe-${local.foundry_agent_account_name}"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = azurerm_subnet.spoke_pe.id
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

# ---- Destroy-time purge so the delegated agent subnet can be removed ----
# Injection creates a serviceAssociationLink on snet-agent; purging the
# soft-deleted account clears it so the subnet destroy does not hit
# InUseSubnetCannotBeDeleted.
resource "time_sleep" "purge_cooldown" {
  destroy_duration = "900s"
  depends_on       = [azurerm_subnet.agent]
}

resource "azapi_resource_action" "purge_foundry_agent_account" {
  method      = "DELETE"
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2021-04-30"
  resource_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${local.rg_name}/deletedAccounts/${local.foundry_agent_account_name}"
  when        = "destroy"

  depends_on = [time_sleep.purge_cooldown]
}
