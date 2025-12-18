# Private DNS Zones
resource "azurerm_private_dns_zone" "cognitive_services" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "storage_blob" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "storage_file" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.file.core.windows.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "storage_table" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.table.core.windows.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "storage_queue" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.queue.core.windows.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "key_vault" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "container_registry" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.azurecr.io"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "openai" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "aifoundry_api" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.api.azureml.ms"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "aifoundry_notebooks" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.notebooks.azure.net"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "aifoundry_services" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.services.ai.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "cosmos" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.documents.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone" "aisearch" {
  count               = var.enable_dns ? 1 : 0
  name                = "privatelink.search.windows.net"
  resource_group_name = azurerm_resource_group.main.name
}

# VNet Links
resource "azurerm_private_dns_zone_virtual_network_link" "cognitive_services" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.cognitive_services[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "storage_blob" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-blob-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.storage_blob[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "storage_file" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-file-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.storage_file[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "storage_table" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-table-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.storage_table[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "storage_queue" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-queue-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.storage_queue[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "key_vault" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-keyvault-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.key_vault[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "container_registry" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-acr-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.container_registry[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-openai-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.openai[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "aifoundry_api" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-aifoundryapi-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.aifoundry_api[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "aifoundry_notebooks" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-aifoundrynb-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.aifoundry_notebooks[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "aifoundry_services" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-aifoundrysvc-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.aifoundry_services[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "cosmos" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-cosmos-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.cosmos[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "aisearch" {
  count                 = var.enable_dns && var.enable_networking ? 1 : 0
  name                  = "${var.vnet_name}-aisearch-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.aisearch[0].name
  virtual_network_id    = azurerm_virtual_network.main[0].id
}
