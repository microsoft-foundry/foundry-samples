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

output "vm_subnet_id" {
  description = "The ID of the VM subnet"
  value       = var.enable_vm ? azurerm_subnet.vms[0].id : null
}

output "bastion_id" {
  description = "The ID of the Azure Bastion"
  value       = var.enable_vm ? azurerm_bastion_host.main[0].id : null
}

output "bastion_dns_name" {
  description = "The DNS name of the Azure Bastion"
  value       = var.enable_vm ? azurerm_bastion_host.main[0].dns_name : null
}

output "windows_vm_id" {
  description = "The ID of the Windows VM"
  value       = var.enable_vm ? azurerm_windows_virtual_machine.main[0].id : null
}

output "windows_vm_private_ip" {
  description = "The private IP address of the Windows VM"
  value       = var.enable_vm ? azurerm_network_interface.vm[0].private_ip_address : null
}

output "windows_vm_computer_name" {
  description = "The computer name of the Windows VM"
  value       = var.enable_vm ? azurerm_windows_virtual_machine.main[0].computer_name : null
}

output "key_vault_id" {
  description = "The ID of the Key Vault"
  value       = var.enable_vm ? azurerm_key_vault.main[0].id : null
}

output "key_vault_name" {
  description = "The name of the Key Vault"
  value       = var.enable_vm ? azurerm_key_vault.main[0].name : null
}

output "key_vault_uri" {
  description = "The URI of the Key Vault"
  value       = var.enable_vm ? azurerm_key_vault.main[0].vault_uri : null
}

output "vm_admin_password_secret_id" {
  description = "The Key Vault secret ID containing the VM admin password"
  value       = var.enable_vm ? azurerm_key_vault_secret.vm_admin_password[0].id : null
  sensitive   = true
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
  value       = "https://${azapi_resource.cognitive_account.name}.cognitiveservices.azure.com/"
}

output "ai_foundry_custom_subdomain" {
  description = "The custom subdomain name of the AI Foundry account"
  value       = try(jsondecode(azapi_resource.cognitive_account.output).properties.customSubDomainName, azapi_resource.cognitive_account.name)
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
  } : {}
}
