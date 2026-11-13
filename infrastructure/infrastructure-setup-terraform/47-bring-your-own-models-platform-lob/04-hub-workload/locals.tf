# hub-base outputs consumed via terraform_remote_state. This is the only
# place hub-workload reads hub-base data; every other .tf file references
# data.terraform_remote_state.hub_base.outputs.<name>.

data "terraform_remote_state" "hub_base" {
  backend = "local"
  config = {
    path = var.hub_base_state_path
  }
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length      = 5
  min_numeric = 2
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

locals {
  hub_rg_name = data.terraform_remote_state.hub_base.outputs.hub_resource_group_name
  hub_rg_id   = data.terraform_remote_state.hub_base.outputs.hub_resource_group_id
  location    = data.terraform_remote_state.hub_base.outputs.hub_location

  apim_subnet_id             = data.terraform_remote_state.hub_base.outputs.apim_subnet_id
  private_endpoint_subnet_id = data.terraform_remote_state.hub_base.outputs.private_endpoint_subnet_id
  private_dns_zone_ids       = data.terraform_remote_state.hub_base.outputs.private_dns_zone_ids

  platform_law_id = data.terraform_remote_state.hub_base.outputs.platform_log_analytics_workspace_id

  random_suffix = random_string.suffix.result

  foundry_model_account_name = lower(replace("${var.name_prefix}models${local.random_suffix}", "-", ""))
  apim_name                  = "${var.name_prefix}-apim-${local.random_suffix}"
  keyvault_name              = substr(lower(replace("${var.name_prefix}kv${local.random_suffix}", "-", "")), 0, 24)
  appi_name                  = "appi-${var.name_prefix}-${local.random_suffix}"

  apim_api_path  = "inference"
  token_audience = "https://cognitiveservices.azure.com"

  common_tags = {
    scenario          = "byom-platform-lob"
    sample            = "47-bring-your-own-models-platform-lob"
    plane             = "hub"
    root              = "hub-workload"
    subscription_role = "platform"
  }

  # --------------------------------------------------------------------------
  # Diagnostic mock alias. Routed in the APIM policy to a constant-latency
  # <return-response> (no upstream call), so client-side A/B timing can
  # isolate the data-proxy hop from real model/backend variance. Listed in
  # the catalog so the gateway connection's model metadata accepts
  # `gateway/mock` at invocation time.
  # --------------------------------------------------------------------------
  mock_alias = "mock"

  # --------------------------------------------------------------------------
  # Approved catalog. Same shape as sample 46 — Foundry / Gemini / Groq,
  # plus the diagnostic mock alias.
  # --------------------------------------------------------------------------
  catalog_aliases = [
    { alias = var.foundry_model_name, vendor = "microsoft-foundry", upstream_model = var.foundry_model_name },
    { alias = var.gemini_alias, vendor = "google-gemini", upstream_model = var.gemini_model_name },
    { alias = var.groq_alias, vendor = "groq-llama", upstream_model = var.groq_model_name },
    { alias = local.mock_alias, vendor = "mock", upstream_model = local.mock_alias },
  ]

  # --------------------------------------------------------------------------
  # APIM gateway hostname used in the published contract.
  #
  # We use the STANDARD `.azure-api.net` hostname (not `.privatelink.azure-api.net`)
  # for two reasons:
  #   1. Foundry's Agent Service (and any TLS client) validates SNI/certificate
  #      against this hostname. APIM's managed TLS cert is issued only for the
  #      standard gateway hostname; using the privatelink hostname causes
  #      "SSL connection could not be established" at runtime.
  #   2. From inside the spoke VNet the FQDN still resolves privately: the
  #      public DNS returns a CNAME to <apim>.privatelink.azure-api.net, which
  #      the linked private DNS zone answers with the PE IP. So the network
  #      path stays private end-to-end.
  # --------------------------------------------------------------------------
  apim_gateway_fqdn          = "${local.apim_name}.azure-api.net"
  apim_gateway_target        = "https://${local.apim_gateway_fqdn}/${local.apim_api_path}"
  apim_public_gateway_target = "${azurerm_api_management.apim.gateway_url}/${local.apim_api_path}" # kept for diagnostics.
}
