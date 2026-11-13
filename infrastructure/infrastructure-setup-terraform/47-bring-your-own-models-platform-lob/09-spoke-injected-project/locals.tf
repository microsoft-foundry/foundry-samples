data "terraform_remote_state" "spoke_base" {
  backend = "local"
  config = {
    path = var.spoke_base_state_path
  }
}

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
  contract = jsondecode(file(var.contract_path))

  # ---- Reused from the existing spoke deployment (02-spoke-base) ----
  spoke_rg_name   = data.terraform_remote_state.spoke_base.outputs.spoke_resource_group_name
  spoke_rg_id     = data.terraform_remote_state.spoke_base.outputs.spoke_resource_group_id
  location        = data.terraform_remote_state.spoke_base.outputs.spoke_location
  spoke_vnet_id   = data.terraform_remote_state.spoke_base.outputs.spoke_vnet_id
  spoke_vnet_name = data.terraform_remote_state.spoke_base.outputs.spoke_vnet_name
  spoke_pe_snet   = data.terraform_remote_state.spoke_base.outputs.private_endpoint_subnet_id

  # ---- Hub-owned DNS zones (already linked to the spoke VNet by
  #      03-network-registration). The injected account PE registers here. ----
  hub_dns_zones = data.terraform_remote_state.hub_base.outputs.private_dns_zone_ids
  foundry_dns_zone_ids = [
    local.hub_dns_zones["privatelink.services.ai.azure.com"],
    local.hub_dns_zones["privatelink.openai.azure.com"],
    local.hub_dns_zones["privatelink.cognitiveservices.azure.com"],
  ]

  random_suffix = random_string.suffix.result

  # Injected Foundry agent account name (valid custom subdomain).
  foundry_agent_account_name = lower(replace("${var.name_prefix}-dp-fdry-${local.random_suffix}", "_", "-"))

  # BYO agent-store resource names (storage <= 24 chars, lowercase alnum).
  storage_name = "byomdp${local.random_suffix}stg"
  cosmos_name  = "byomdp${local.random_suffix}cos"
  search_name  = "byomdp${local.random_suffix}search"

  # ---- Contract handshake with the platform gateway (identical to 05) ----
  gateway_private_url = local.contract.gateway.private_url
  gateway_audience    = local.contract.gateway.audience
  gateway_api_version = local.contract.gateway.inference_api_version
  approved_catalog    = local.contract.catalog.aliases
  catalog_version     = local.contract.catalog.version

  approved_catalog_models_json = jsonencode([
    for m in local.approved_catalog : {
      name = m.alias
      properties = {
        model = {
          name    = m.alias
          version = "1"
          format  = "OpenAI"
        }
      }
    }
  ])

  gateway_connection_metadata = {
    audience            = local.gateway_audience
    deploymentInPath    = "true"
    inferenceAPIVersion = local.gateway_api_version
    models              = local.approved_catalog_models_json
    customHeaders       = "{}"
    authConfig          = "{}"
  }

  common_tags = {
    scenario          = "byom-platform-lob-dataproxy"
    sample            = "47-bring-your-own-models-platform-lob"
    plane             = "spoke"
    root              = "spoke-workload/injected-project"
    subscription_role = "lob"
    lob               = var.name_prefix
    variant           = "vnet-injected-dataproxy"
  }
}
