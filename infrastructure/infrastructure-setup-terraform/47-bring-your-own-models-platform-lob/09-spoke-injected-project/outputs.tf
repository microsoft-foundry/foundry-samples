output "foundry_agent_account_name" {
  description = "Injected Foundry agent account name."
  value       = azapi_resource.foundry_agent_account.name
}

output "foundry_agent_account_id" {
  description = "Injected Foundry agent account id."
  value       = azapi_resource.foundry_agent_account.id
}

output "project_name" {
  description = "Foundry project name."
  value       = azapi_resource.project.name
}

output "project_endpoint" {
  description = "Projects-scoped data-plane endpoint. Use this for the Path A Responses API call from the jumpbox."
  value       = "https://${local.foundry_agent_account_name}.services.ai.azure.com/api/projects/${azapi_resource.project.name}"
}

output "project_managed_identity_object_id" {
  description = <<-EOT
    Object ID of the project's system-assigned managed identity. REQUIRED
    POST-STEP: paste this into 06-hub-allowlist/allowlist.auto.tfvars and
    re-apply 06, or the BYOG gateway call returns 401 (oid not allowlisted).
  EOT
  value       = azapi_resource.project.output.identity.principalId
}

output "connection_name" {
  description = "BYOG APIM connection name attached to the project."
  value       = azapi_resource.connection_gateway.name
}

output "agent_subnet_id" {
  description = "Delegated Standard-Agent subnet id added to the spoke VNet."
  value       = azurerm_subnet.agent.id
}

output "gateway_model_example" {
  description = "Example model value for the Responses API (connection/alias)."
  value       = "gateway/${try(local.approved_catalog[0].alias, "gpt-4.1")}"
}
