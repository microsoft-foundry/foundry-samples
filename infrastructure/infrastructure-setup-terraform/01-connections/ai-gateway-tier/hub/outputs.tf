output "subscription_id" {
  description = "Hub subscription."
  value       = var.subscription_id
}

output "resource_group_name" {
  description = "Hub resource group."
  value       = local.resource_group_name
}

output "account_name" {
  description = "Hub Foundry account name."
  value       = azapi_resource.account.name
}

output "account_id" {
  description = "Hub Foundry account resource ID."
  value       = azapi_resource.account.id
}

output "project_id" {
  description = "Hub project resource ID. You can attach the connection here for a quick single-project test."
  value       = azapi_resource.project.id
}

output "gateway_id" {
  description = "AI Gateway resource ID. Pass it to ../connection as gateway_id."
  value       = module.ai_gateway.gateway_id
}

output "gateway_name" {
  description = "AI Gateway name."
  value       = module.ai_gateway.gateway_name
}

output "gateway_principal_id" {
  description = "Object ID of the gateway's managed identity (grant it Foundry User on the hub account if assign_foundry_user_role = false)."
  value       = module.ai_gateway.gateway_principal_id
}

output "gateway_models_base_url" {
  description = "OpenAI v1 base URL for direct calls through the gateway."
  value       = module.ai_gateway.models_base_url
}

output "model_name" {
  description = "Callable model name (alias). Pass it to ../connection as model_name."
  value       = module.ai_gateway.alias_name
}

output "model_version" {
  description = "Model version. Pass it to ../connection as model_version."
  value       = var.model_version
}

output "api_key_name" {
  description = "Runtime API key name. Pass it to ../connection as api_key_name."
  value       = module.ai_gateway.api_key_name
}
