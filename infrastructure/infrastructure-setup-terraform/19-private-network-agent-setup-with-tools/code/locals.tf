########## Local values
##########

locals {
  ## Naming
  account_name = lower("${var.ai_services_name_prefix}${random_string.unique.result}")

  ## Subnet CIDRs (used only when creating new subnets)
  subnet_agent_address_prefix = cidrsubnet(var.vnet_address_space[0], 8, 0)
  subnet_pe_address_prefix    = cidrsubnet(var.vnet_address_space[0], 8, 1)
  subnet_mcp_address_prefix   = cidrsubnet(var.vnet_address_space[0], 8, 2)

  ## Project GUID (derived from project internalId after project creation)
  project_id_guid = "${substr(azapi_resource.ai_project.output.properties.internalId, 0, 8)}-${substr(azapi_resource.ai_project.output.properties.internalId, 8, 4)}-${substr(azapi_resource.ai_project.output.properties.internalId, 12, 4)}-${substr(azapi_resource.ai_project.output.properties.internalId, 16, 4)}-${substr(azapi_resource.ai_project.output.properties.internalId, 20, 12)}"

  ########## BYO flags — true when we need to create the resource
  ##########
  create_rg      = var.existing_resource_group_name == ""
  create_vnet    = var.existing_vnet_id == ""
  create_storage = var.existing_storage_account_id == ""
  create_cosmos  = var.existing_cosmosdb_account_id == ""
  create_search  = var.existing_ai_search_id == ""
  create_fabric  = var.existing_fabric_workspace_id != ""

  ## DNS zones — create when no existing resource group provided
  create_dns_zones      = var.existing_dns_zones_resource_group == ""
  dns_zones_sub_id      = coalesce(var.existing_dns_zones_subscription_id, data.azurerm_client_config.current.subscription_id)
  dns_zones_rg          = var.existing_dns_zones_resource_group

  ########## Unified resource references
  ########## All downstream code uses these locals instead of direct resource references.
  ##########

  ## Resource Group
  rg_name = local.create_rg ? azurerm_resource_group.rg[0].name : var.existing_resource_group_name
  rg_id   = local.create_rg ? azurerm_resource_group.rg[0].id : "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.existing_resource_group_name}"

  ## VNet
  vnet_id      = local.create_vnet ? azurerm_virtual_network.vnet[0].id : var.existing_vnet_id
  vnet_name    = local.create_vnet ? azurerm_virtual_network.vnet[0].name : split("/", var.existing_vnet_id)[8]
  vnet_rg_name = local.create_vnet ? local.rg_name : split("/", var.existing_vnet_id)[4]

  ## Subnets
  subnet_agent_id = var.existing_agent_subnet_id != "" ? var.existing_agent_subnet_id : azurerm_subnet.subnet_agent[0].id
  subnet_pe_id    = var.existing_pe_subnet_id != "" ? var.existing_pe_subnet_id : azurerm_subnet.subnet_pe[0].id
  subnet_mcp_id   = var.existing_mcp_subnet_id != "" ? var.existing_mcp_subnet_id : azurerm_subnet.subnet_mcp[0].id

  ## Storage Account
  storage_id       = local.create_storage ? azurerm_storage_account.storage_account[0].id : var.existing_storage_account_id
  storage_name     = local.create_storage ? azurerm_storage_account.storage_account[0].name : split("/", var.existing_storage_account_id)[8]
  storage_endpoint = local.create_storage ? azurerm_storage_account.storage_account[0].primary_blob_endpoint : data.azurerm_storage_account.existing[0].primary_blob_endpoint
  storage_location = local.create_storage ? var.location : data.azurerm_storage_account.existing[0].location

  ## Cosmos DB
  cosmos_id       = local.create_cosmos ? azurerm_cosmosdb_account.cosmosdb[0].id : var.existing_cosmosdb_account_id
  cosmos_name     = local.create_cosmos ? azurerm_cosmosdb_account.cosmosdb[0].name : split("/", var.existing_cosmosdb_account_id)[8]
  cosmos_rg_name  = local.create_cosmos ? local.rg_name : split("/", var.existing_cosmosdb_account_id)[4]
  cosmos_endpoint = local.create_cosmos ? azurerm_cosmosdb_account.cosmosdb[0].endpoint : data.azurerm_cosmosdb_account.existing[0].endpoint
  cosmos_location = local.create_cosmos ? var.location : data.azurerm_cosmosdb_account.existing[0].location

  ## AI Search
  search_id       = local.create_search ? azapi_resource.ai_search[0].id : var.existing_ai_search_id
  search_name     = local.create_search ? azapi_resource.ai_search[0].name : split("/", var.existing_ai_search_id)[8]
  search_location = local.create_search ? var.location : data.azapi_resource.existing_search[0].output.location

  ## Fabric (BYO-only, never created — only PE + DNS when workspace ID provided)
  fabric_name = local.create_fabric ? split("/", var.existing_fabric_workspace_id)[8] : ""

  ## DNS Zone IDs — construct from subscription/RG/name when BYO, otherwise use created resource
  dns_zone_cognitive_services_id = local.create_dns_zones ? azurerm_private_dns_zone.plz_cognitive_services[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
  dns_zone_openai_id             = local.create_dns_zones ? azurerm_private_dns_zone.plz_openai[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"
  dns_zone_ai_services_id        = local.create_dns_zones ? azurerm_private_dns_zone.plz_ai_services[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com"
  dns_zone_search_id             = local.create_dns_zones ? azurerm_private_dns_zone.plz_ai_search[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net"
  dns_zone_storage_blob_id       = local.create_dns_zones ? azurerm_private_dns_zone.plz_storage_blob[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  dns_zone_cosmos_db_id          = local.create_dns_zones ? azurerm_private_dns_zone.plz_cosmos_db[0].id : "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com"
  dns_zone_fabric_id             = local.create_dns_zones && local.create_fabric ? azurerm_private_dns_zone.plz_fabric[0].id : local.create_fabric ? "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.fabric.microsoft.com" : ""
  dns_zone_acr_id                = var.enable_container_registry && local.create_dns_zones ? azurerm_private_dns_zone.plz_acr[0].id : var.enable_container_registry ? "/subscriptions/${local.dns_zones_sub_id}/resourceGroups/${local.dns_zones_rg}/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io" : ""
}
