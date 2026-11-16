# ============================================================================
# Private DNS zones + VNet links (hub-owned, linked to hub and spoke).
#
# Both VNets must resolve these names privately:
#   * spoke - the data proxy resolves the gateway hostname (var.custom_domain_zone)
#     and the Foundry account / BYO store endpoints.
#   * hub   - Application Gateway resolves APIM (azure-api.net) and APIM
#     resolves the private model account (openai / cognitiveservices).
# The gateway zone is internal-only, mirroring an enterprise gateway that
# does not resolve externally.
# ============================================================================

locals {
  dns_zones = {
    cognitiveservices = "privatelink.cognitiveservices.azure.com"
    openai            = "privatelink.openai.azure.com"
    services_ai       = "privatelink.services.ai.azure.com"
    apim              = "privatelink.azure-api.net"
    blob              = "privatelink.blob.core.windows.net"
    cosmos            = "privatelink.documents.azure.com"
    search            = "privatelink.search.windows.net"
  }
}

resource "azurerm_private_dns_zone" "cognitiveservices" {
  name                = local.dns_zones.cognitiveservices
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "openai" {
  name                = local.dns_zones.openai
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "services_ai" {
  name                = local.dns_zones.services_ai
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "apim" {
  name                = local.dns_zones.apim
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "blob" {
  name                = local.dns_zones.blob
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "cosmos" {
  name                = local.dns_zones.cosmos
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "search" {
  name                = local.dns_zones.search
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

# Gateway hostname zone (internal-only; enterprise gateway behind private DNS).
resource "azurerm_private_dns_zone" "custom" {
  name                = var.custom_domain_zone
  resource_group_name = local.rg_name
  tags                = local.common_tags
}

locals {
  all_dns_zones = merge(
    local.dns_zones,
    { custom = var.custom_domain_zone },
  )
}

# ---- Link every zone to the spoke VNet ----
resource "azurerm_private_dns_zone_virtual_network_link" "spoke" {
  for_each = local.all_dns_zones

  name                  = "${each.key}-${local.random_suffix}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = each.value
  virtual_network_id    = azurerm_virtual_network.spoke.id
  registration_enabled  = false

  depends_on = [
    azurerm_private_dns_zone.cognitiveservices,
    azurerm_private_dns_zone.openai,
    azurerm_private_dns_zone.services_ai,
    azurerm_private_dns_zone.apim,
    azurerm_private_dns_zone.blob,
    azurerm_private_dns_zone.cosmos,
    azurerm_private_dns_zone.search,
    azurerm_private_dns_zone.custom,
  ]
}

moved {
  from = azurerm_private_dns_zone_virtual_network_link.links
  to   = azurerm_private_dns_zone_virtual_network_link.spoke
}

# ---- Link every zone to the hub VNet ----
resource "azurerm_private_dns_zone_virtual_network_link" "hub" {
  for_each = local.all_dns_zones

  name                  = "${each.key}-hub-${local.random_suffix}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = each.value
  virtual_network_id    = azurerm_virtual_network.hub.id
  registration_enabled  = false

  depends_on = [
    azurerm_private_dns_zone.cognitiveservices,
    azurerm_private_dns_zone.openai,
    azurerm_private_dns_zone.services_ai,
    azurerm_private_dns_zone.apim,
    azurerm_private_dns_zone.blob,
    azurerm_private_dns_zone.cosmos,
    azurerm_private_dns_zone.search,
    azurerm_private_dns_zone.custom,
  ]
}

# ---- Gateway hostname A record -> Application Gateway private IP (hub) ----
# The data proxy in the spoke resolves this name through the spoke link and
# reaches the hub gateway over peering. The certificate served there is issued
# by the private root CA with SAN = local.custom_domain_fqdn.
resource "azurerm_private_dns_a_record" "gateway" {
  name                = var.custom_domain_host
  zone_name           = azurerm_private_dns_zone.custom.name
  resource_group_name = local.rg_name
  ttl                 = 60
  records             = [var.appgw_private_ip]
}
