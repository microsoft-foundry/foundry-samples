# Outputs
output "resource_group_name" {
  description = "The name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "The location of the resource group"
  value       = azurerm_resource_group.main.location
}

output "vnet_id" {
  description = "The ID of the virtual network"
  value       = var.enable_networking ? azurerm_virtual_network.main[0].id : null
}

output "vnet_name" {
  description = "The name of the virtual network"
  value       = var.enable_networking ? azurerm_virtual_network.main[0].name : null
}

output "private_endpoints_subnet_id" {
  description = "The ID of the private endpoints subnet"
  value       = var.enable_networking ? azurerm_subnet.private_endpoints[0].id : null
}

output "storage_account_id" {
  description = "The ID of the storage account"
  value       = var.enable_storage ? azurerm_storage_account.main[0].id : null
}

output "storage_account_name" {
  description = "The name of the storage account"
  value       = var.enable_storage ? azurerm_storage_account.main[0].name : null
}

output "cosmos_account_id" {
  description = "The ID of the Cosmos DB account"
  value       = var.enable_cosmos ? azurerm_cosmosdb_account.main[0].id : null
}

output "cosmos_account_name" {
  description = "The name of the Cosmos DB account"
  value       = var.enable_cosmos ? azurerm_cosmosdb_account.main[0].name : null
}

output "cosmos_account_endpoint" {
  description = "The endpoint of the Cosmos DB account"
  value       = var.enable_cosmos ? azurerm_cosmosdb_account.main[0].endpoint : null
}

output "aisearch_id" {
  description = "The ID of the AI Search service"
  value       = var.enable_aisearch ? azurerm_search_service.main[0].id : null
}

output "aisearch_name" {
  description = "The name of the AI Search service"
  value       = var.enable_aisearch ? azurerm_search_service.main[0].name : null
}

output "aisearch_endpoint" {
  description = "The endpoint of the AI Search service"
  value       = var.enable_aisearch ? "https://${azurerm_search_service.main[0].name}.search.windows.net" : null
}

output "ai_foundry_id" {
  description = "The ID of the AI Foundry / Cognitive Services account"
  value       = azapi_resource.cognitive_account.id
}

output "ai_foundry_name" {
  description = "The name of the AI Foundry / Cognitive Services account"
  value       = azapi_resource.cognitive_account.name
}

output "ai_foundry_endpoint" {
  description = "The endpoint of the AI Foundry / Cognitive Services account"
  value       = try(jsondecode(azapi_resource.cognitive_account.output).properties.endpoint, "")
}

output "ai_foundry_principal_id" {
  description = "The principal ID of the AI Foundry managed identity"
  value       = azapi_resource.cognitive_account.identity[0].principal_id
  sensitive   = true
}

output "private_dns_zone_ids" {
  description = "Map of private DNS zone IDs"
  value = var.enable_dns ? {
    cognitive_services    = azurerm_private_dns_zone.cognitive_services[0].id
    storage_blob          = azurerm_private_dns_zone.storage_blob[0].id
    storage_file          = azurerm_private_dns_zone.storage_file[0].id
    storage_table         = azurerm_private_dns_zone.storage_table[0].id
    storage_queue         = azurerm_private_dns_zone.storage_queue[0].id
    key_vault             = azurerm_private_dns_zone.key_vault[0].id
    container_registry    = azurerm_private_dns_zone.container_registry[0].id
    openai                = azurerm_private_dns_zone.openai[0].id
    aifoundry_api         = azurerm_private_dns_zone.aifoundry_api[0].id
    aifoundry_notebooks   = azurerm_private_dns_zone.aifoundry_notebooks[0].id
    aifoundry_services    = azurerm_private_dns_zone.aifoundry_services[0].id
    cosmos                = azurerm_private_dns_zone.cosmos[0].id
    aisearch              = azurerm_private_dns_zone.aisearch[0].id
    aifoundry_services    = azurerm_private_dns_zone.aifoundry_services[0].id
  } : {}
}
