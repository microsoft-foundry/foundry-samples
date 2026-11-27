output "connection_name" {
  description = "Name of the connection created on the spoke project."
  value       = module.connection.connection_name
}

output "model_reference" {
  description = "Model value for a prompt agent (<connection_name>/<model_name>), for example ai-gateway/gpt-5.4."
  value       = module.connection.model_reference
}

output "project_endpoint" {
  description = "Spoke project endpoint for the Foundry SDK (--endpoint of create-agent.py)."
  value       = module.connection.project_endpoint
}
