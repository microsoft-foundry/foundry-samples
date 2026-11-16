output "resource_group_name" {
  description = "Resource group holding all sample resources."
  value       = local.rg_name
}

output "location" {
  value = var.location
}

output "foundry_agent_account_name" {
  description = "VNet-injected Foundry agent account (hosts the project + data proxy)."
  value       = local.foundry_agent_account_name
}

output "foundry_agent_account_id" {
  value = azapi_resource.foundry_agent_account.id
}

output "project_name" {
  value = azapi_resource.project.name
}

output "project_id" {
  value = azapi_resource.project.id
}

output "project_principal_id" {
  description = "Project managed-identity object id (the connected-model caller)."
  value       = azapi_resource.project.identity[0].principal_id
}

output "foundry_model_endpoint" {
  description = "Private Foundry model account endpoint that APIM forwards to through its VNet integration."
  value       = local.foundry_model_endpoint
}

output "apim_name" {
  value = azurerm_api_management.apim.name
}

output "apim_default_gateway_url" {
  description = "APIM default (public-cert) gateway URL. Application Gateway's backend; NOT the connected-model target."
  value       = azurerm_api_management.apim.gateway_url
}

output "application_gateway_name" {
  value = azurerm_application_gateway.gateway.name
}

output "application_gateway_private_ip" {
  description = "Hub Application Gateway private frontend IP serving the private-CA certificate on the gateway hostname."
  value       = var.appgw_private_ip
}

output "hub_vnet_name" {
  value = azurerm_virtual_network.hub.name
}

output "spoke_vnet_name" {
  value = azurerm_virtual_network.spoke.name
}

output "gateway_custom_domain_fqdn" {
  description = "Gateway hostname behind private DNS. Internal-only; resolves to the hub Application Gateway from both VNets."
  value       = local.custom_domain_fqdn
}

output "connected_model_target" {
  description = "Connected-model target URL. The spoke data proxy validates this hostname's certificate against the registered private root CA."
  value       = local.gateway_target
}

output "key_vault_name" {
  value = azurerm_key_vault.kv.name
}

output "gateway_certificate_name" {
  description = "Key Vault certificate (leaf + root chain) served by Application Gateway on the gateway hostname."
  value       = local.gateway_cert_name
}

output "gateway_certificate_version" {
  description = "Version of the Key Vault certificate served on the gateway hostname."
  value       = azurerm_key_vault_certificate.gateway.version
}

output "root_ca_certificate_pem" {
  description = "Private root CA public certificate (trust anchor). Not secret."
  value       = tls_self_signed_cert.root_ca.cert_pem
}

output "root_ca_secret_name" {
  description = "Key Vault SECRET (root CA public PEM) referenced by account.trustedCertificateSources."
  value       = local.root_ca_secret_name
}

output "root_ca_secret_version" {
  description = "Pinned version of the root CA secret registered in account.trustedCertificateSources."
  value       = azurerm_key_vault_secret.root_ca_pem.version
}
