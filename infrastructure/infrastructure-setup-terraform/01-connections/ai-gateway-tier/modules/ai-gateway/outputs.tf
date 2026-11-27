output "gateway_id" {
  description = "Resource ID of the AI Gateway."
  value       = azapi_resource.gateway.id
}

output "gateway_name" {
  description = "Name of the AI Gateway."
  value       = azapi_resource.gateway.name
}

output "gateway_principal_id" {
  description = "Principal ID of the gateway's system-assigned managed identity."
  value       = azapi_resource.gateway.identity[0].principal_id
}

output "gateway_hostname" {
  description = "Runtime host name assigned by the service (properties.frontend.defaultHostname). Don't construct it from the gateway name."
  value       = azapi_resource.gateway.output.properties.frontend.defaultHostname
}

output "models_base_url" {
  description = "OpenAI v1 base URL for model calls through the gateway."
  value       = "https://${azapi_resource.gateway.output.properties.frontend.defaultHostname}/default/models/openai/v1"
}

output "model_id" {
  description = "Resource ID of the gateway model registration."
  value       = azapi_resource.model.id
}

output "alias_name" {
  description = "Callable model name to send in the request \"model\" field."
  value       = azapi_resource.alias.name
}

output "api_key_name" {
  description = "Name of the runtime API key."
  value       = azapi_resource.api_key.name
}

# Built from the create response so it stays unknown until the key exists; an
# ephemeral listSecrets that consumes it is then deferred to apply time.
output "api_key_id" {
  description = "Resource ID of the runtime API key (read its value with listSecrets)."
  value       = "${azapi_resource.gateway.id}/apiKeys/${azapi_resource.api_key.output.name}"
}
