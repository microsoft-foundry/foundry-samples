output "resource_group_name" {
  description = "Resource group that holds everything in this sample."
  value       = azurerm_resource_group.rg.name
}

output "account_name" {
  description = "The agent's Foundry account."
  value       = azapi_resource.foundry.name
}

output "project_endpoint" {
  description = "Project endpoint for the Foundry SDK (--endpoint of create-agent.py). Reachable only from the VNet unless foundry_allowed_ip_ranges is set."
  value       = module.connection.project_endpoint
}

output "model_reference" {
  description = "Model value for a prompt agent (<connection_name>/<model_name>)."
  value       = module.connection.model_reference
}

output "hub_account_name" {
  description = "Private hub Foundry account that hosts the model."
  value       = azapi_resource.hub_account.name
}

output "gateway_id" {
  description = "AI Gateway resource ID."
  value       = module.ai_gateway.gateway_id
}

output "gateway_name" {
  description = "AI Gateway name."
  value       = module.ai_gateway.gateway_name
}

output "gateway_principal_id" {
  description = "Object ID of the gateway's managed identity."
  value       = module.ai_gateway.gateway_principal_id
}

output "gateway_models_base_url" {
  description = "OpenAI v1 base URL for direct calls through the gateway (public inbound)."
  value       = module.ai_gateway.models_base_url
}

output "api_key_name" {
  description = "Runtime API key name (read its value with listSecrets)."
  value       = module.ai_gateway.api_key_name
}
