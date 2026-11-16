# ============================================================================
# Client config, randomness, and shared computed values.
# ============================================================================

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
  tenant_id     = data.azurerm_client_config.current.tenant_id
  random_suffix = random_string.suffix.result

  # ------------------------------------------------------------------------
  # Naming.
  # ------------------------------------------------------------------------
  create_rg = var.existing_resource_group_name == ""
  rg_name   = local.create_rg ? azurerm_resource_group.rg[0].name : data.azurerm_resource_group.existing[0].name
  rg_id     = local.create_rg ? azurerm_resource_group.rg[0].id : data.azurerm_resource_group.existing[0].id

  foundry_model_account_name = lower(replace("${var.name_prefix}models${local.random_suffix}", "-", ""))
  foundry_agent_account_name = lower(replace("${var.name_prefix}agents${local.random_suffix}", "-", ""))

  apim_name     = "${var.name_prefix}-apim-${local.random_suffix}"
  appgw_name    = "agw-${var.name_prefix}-${local.random_suffix}"
  keyvault_name = substr(lower(replace("${var.name_prefix}kv${local.random_suffix}", "-", "")), 0, 24)
  law_name      = "law-${var.name_prefix}-${local.random_suffix}"
  appi_name     = "appi-${var.name_prefix}-${local.random_suffix}"

  # The spoke keeps the original VNet name so existing deployments are not
  # recreated; the hub is named explicitly.
  spoke_vnet_name = "vnet-${var.name_prefix}-${local.random_suffix}"
  hub_vnet_name   = "vnet-${var.name_prefix}-hub-${local.random_suffix}"

  storage_name = substr(lower(replace("${var.name_prefix}stg${local.random_suffix}", "-", "")), 0, 24)
  cosmos_name  = lower("${var.name_prefix}-cosmos-${local.random_suffix}")
  search_name  = lower("${var.name_prefix}-search-${local.random_suffix}")

  # ------------------------------------------------------------------------
  # Gateway hostname + trust material.
  #   * gateway_cert_name      -> KV certificate (PFX: leaf + key + root chain)
  #     that Application Gateway serves on the gateway hostname.
  #   * root_ca_secret_name    -> KV SECRET holding the private root CA PUBLIC
  #     PEM, referenced by account.trustedCertificateSources. The resolver reads
  #     a KV SECRET (PEM bundle), not a certificate object.
  # ------------------------------------------------------------------------
  custom_domain_fqdn  = "${var.custom_domain_host}.${var.custom_domain_zone}"
  gateway_cert_name   = "gateway-tls"
  root_ca_secret_name = "private-root-ca-pem"

  # Public-preview trust contract. Pinned secretVersion is required.
  trusted_certificate_sources = [
    {
      type       = "AzureKeyVault"
      resourceId = azurerm_key_vault.kv.id
      certificateBundleReferences = [
        {
          secretName    = local.root_ca_secret_name
          secretVersion = azurerm_key_vault_secret.root_ca_pem.version
        }
      ]
    }
  ]

  # ------------------------------------------------------------------------
  # APIM API path, token audience, and the connected-model target.
  # ------------------------------------------------------------------------
  apim_api_path  = "inference"
  token_audience = "https://cognitiveservices.azure.com"

  # The connected model targets the private-DNS gateway hostname served by
  # Application Gateway with the private-CA certificate.
  gateway_target = "https://${local.custom_domain_fqdn}/${local.apim_api_path}"

  # Backend the APIM policy forwards to (the private Foundry model account).
  foundry_model_endpoint = "https://${local.foundry_model_account_name}.openai.azure.com"

  # Cognitive Services IP rules take bare addresses for single hosts.
  foundry_allowed_ip_rules = [for range in var.foundry_allowed_ip_ranges : trimsuffix(range, "/32")]

  # ------------------------------------------------------------------------
  # Approved catalog surfaced on the connected model (single model here).
  # metadata.models must be a JSON *string* for the Foundry portal picker.
  # ------------------------------------------------------------------------
  approved_catalog_models_json = jsonencode([
    {
      name = var.foundry_model_name
      properties = {
        model = {
          name    = var.foundry_model_name
          version = "1"
          format  = "OpenAI"
        }
      }
    }
  ])

  gateway_connection_metadata = {
    audience            = local.token_audience
    deploymentInPath    = "true"
    inferenceAPIVersion = var.inference_api_version
    models              = local.approved_catalog_models_json
    customHeaders       = "{}"
    authConfig          = "{}"
  }

  # ------------------------------------------------------------------------
  # Private DNS zones (hub-owned, linked to both hub and spoke VNets).
  #   * Foundry accounts: cognitiveservices / openai / services.ai
  #   * APIM private endpoint: azure-api.net
  #   * Store private endpoints: blob / documents / search
  #   * Gateway hostname: var.custom_domain_zone
  # ------------------------------------------------------------------------
  foundry_dns_zone_ids = [
    azurerm_private_dns_zone.cognitiveservices.id,
    azurerm_private_dns_zone.openai.id,
    azurerm_private_dns_zone.services_ai.id,
  ]

  common_tags = {
    scenario = "byom-private-ca"
    sample   = "48-bring-own-model-private-ca"
  }
}
