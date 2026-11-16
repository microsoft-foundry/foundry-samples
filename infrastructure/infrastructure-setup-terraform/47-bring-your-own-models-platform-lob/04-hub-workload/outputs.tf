output "apim_name" {
  description = "APIM name. Consumed by hub-allowlist to look up the API management service."
  value       = azurerm_api_management.apim.name
}

output "apim_resource_group_name" {
  description = "Resource group that owns APIM. Consumed by hub-allowlist."
  value       = local.hub_rg_name
}

output "apim_inference_api_name" {
  description = "APIM API name that the JWT allowlist policy is attached to. Consumed by hub-allowlist."
  value       = azurerm_api_management_api.inference.name
}

output "apim_private_gateway_url" {
  description = "Private gateway URL published in the contract. Spokes call this URL, not the public one."
  value       = local.apim_gateway_target
}

output "foundry_model_account_id" {
  description = "Foundry model account id — kept as an output for observability."
  value       = azapi_resource.foundry_model_account.id
}

output "contract_path" {
  description = "Path to the published contract JSON file."
  value       = var.contract_output_path
}

output "catalog_aliases" {
  description = "Model aliases exposed through the gateway. Same list as contracts/hub-workload.contract.json → catalog.aliases."
  value       = local.catalog_aliases
}

output "token_audience" {
  description = "APIM validate-azure-ad-token audience. Consumed by hub-allowlist and by the spoke Foundry connection body."
  value       = local.token_audience
}

output "tenant_id" {
  description = "Tenant used for APIM validate-azure-ad-token. Consumed by hub-allowlist."
  value       = var.tenant_id
}

output "quota_tokens_per_minute" {
  description = "Token quota parameter passed through to the APIM policy. Consumed by hub-allowlist so both roots render the same body."
  value       = var.quota_tokens_per_minute
}

output "policy_render_inputs" {
  description = "Bundle of policy render inputs (catalog aliases, upstream URLs, model names) that hub-allowlist re-uses when it renders the SAME apim-policy.xml.tftpl with an updated allowlist."
  value = {
    foundry_endpoint = "https://${local.foundry_model_account_name}.openai.azure.com"
    foundry_alias    = var.foundry_model_name
    gemini_alias     = var.gemini_alias
    gemini_upstream  = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model     = var.gemini_model_name
    groq_alias       = var.groq_alias
    groq_upstream    = "https://api.groq.com/openai/v1"
    groq_model       = var.groq_model_name

    mock_alias = local.mock_alias
  }
}
