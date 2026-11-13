output "resource_group_name" {
  description = "The name of the resource group"
  value       = local.rg_name
}

output "vnet_id" {
  description = "The ID of the virtual network"
  value       = local.vnet_id
}

output "ai_foundry_id" {
  description = "The ID of the AI Foundry account"
  value       = azapi_resource.ai_foundry.id
}

output "storage_account_id" {
  description = "The ID of the storage account"
  value       = local.storage_id
}

output "search_service_id" {
  description = "The ID of the AI Search service"
  value       = local.search_id
}

output "cosmos_db_id" {
  description = "The ID of the Cosmos DB account"
  value       = local.cosmos_id
}
