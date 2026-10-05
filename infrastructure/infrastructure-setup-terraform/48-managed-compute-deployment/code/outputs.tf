output "deployment_resource_id" {
  description = "ARM resource ID of the managed-compute deployment."
  value       = azapi_resource.managed_compute_deployment.id
}

output "deployment_name" {
  description = "Name of the managed-compute deployment."
  value       = azapi_resource.managed_compute_deployment.name
}

output "accelerator_type" {
  description = "Managed-compute accelerator family."
  value       = var.accelerator_type
}

output "capacity" {
  description = "Number of model instances."
  value       = var.capacity
}
