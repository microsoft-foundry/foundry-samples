output "connection_name" {
  description = "Connection name. Agents reference a model as <connection_name>/<model-name>."
  value       = azapi_resource.connection.name
}

output "connection_id" {
  description = "Resource ID of the connection."
  value       = azapi_resource.connection.id
}

output "target_url" {
  description = "API Management gateway URL plus the API's path."
  value       = local.target_url
}

output "auth_type" {
  description = "Authentication type of the connection."
  value       = var.auth_type
}

output "metadata" {
  description = "Metadata sent with the connection."
  value       = local.metadata
}

output "has_static_models" {
  description = "Whether the connection lists static models."
  value       = local.has_static_models
}

output "has_model_discovery" {
  description = "Whether the connection discovers models dynamically."
  value       = local.has_model_discovery
}

output "has_custom_headers" {
  description = "Whether the connection sends custom headers."
  value       = length(var.custom_headers) > 0
}
