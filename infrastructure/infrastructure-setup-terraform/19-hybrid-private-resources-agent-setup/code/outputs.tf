output "resource_group_name" {
  description = "The name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "vnet_id" {
  description = "The ID of the virtual network"
  value       = azurerm_virtual_network.vnet.id
}

output "ai_foundry_id" {
  description = "The ID of the AI Foundry account"
  value       = azapi_resource.ai_foundry.id
}

output "ai_project_id" {
  description = "The ID of the AI Foundry project"
  value       = azapi_resource.ai_project.id
}

output "storage_account_id" {
  description = "The ID of the storage account"
  value       = azurerm_storage_account.storage.id
}

output "search_service_id" {
  description = "The ID of the AI Search service"
  value       = azurerm_search_service.search.id
}

output "cosmos_db_id" {
  description = "The ID of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.cosmos.id
}

output "deployment_summary" {
  description = "Summary of public vs private resources"
  value = {
    ai_foundry_access = var.ai_foundry_public_access
    storage_access    = var.storage_public_access ? "Public" : "Private"
    search_access     = var.search_public_access ? "Public" : "Private"
    cosmos_access     = var.cosmos_public_access ? "Public" : "Private"
  }
}
