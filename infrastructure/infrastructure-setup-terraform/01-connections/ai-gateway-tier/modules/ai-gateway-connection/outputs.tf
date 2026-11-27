output "connection_id" {
  description = "Resource ID of the connection."
  value       = azapi_resource.connection.id
}

output "connection_name" {
  description = "Name of the connection."
  value       = azapi_resource.connection.name
}

output "model_reference" {
  description = "Model value for a prompt agent: <connection_name>/<model_name>."
  value       = "${azapi_resource.connection.name}/${var.model_name}"
}

output "project_endpoint" {
  description = "Project endpoint for the Foundry SDK."
  value       = "https://${data.azapi_resource.account.output.properties.customSubDomainName}.services.ai.azure.com/api/projects/${local.project_name}"
}
