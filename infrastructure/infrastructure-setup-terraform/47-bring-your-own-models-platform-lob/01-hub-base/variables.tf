# ============================================================================
# Subscription and location inputs
# ============================================================================

variable "platform_subscription_id" {
  description = "Subscription ID for the Platform (hub) subscription. Hosts hub networking, Firewall, Bastion, platform Log Analytics, and the H-series Azure Policy assignments."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant ID. Required because the azapi provider does not auto-detect tenant from subscription."
  type        = string
}

variable "location" {
  description = "Azure region for all hub resources."
  type        = string
  default     = "swedencentral"

  validation {
    condition = contains([
      "australiaeast", "brazilsouth", "canadacentral", "canadaeast", "centralindia", "centralus",
      "eastasia", "eastus", "francecentral", "germanywestcentral", "italynorth", "japaneast",
      "koreacentral", "northcentralus", "northeurope", "norwayeast", "qatarcentral", "southafricanorth",
      "southcentralus", "southindia", "southeastasia", "spaincentral", "swedencentral", "switzerlandnorth",
      "uaenorth", "uksouth", "usgovarizona", "usgovvirginia", "westeurope", "westus", "westus3",
    ], var.location)
    error_message = "The location must be a supported Microsoft Foundry region."
  }
}

variable "name_prefix" {
  description = "Prefix for hub resource names. Kept short because Firewall, Bastion, and DNS zones inherit derived names."
  type        = string
  default     = "contoso-byom"
}

# ============================================================================
# Networking
# ============================================================================

variable "hub_vnet_address_space" {
  description = "CIDR block for the hub VNet. Must not overlap with any spoke VNet — coordinated through the network-registration root."
  type        = list(string)
  default     = ["10.10.0.0/16"]
}

variable "firewall_subnet_prefix" {
  description = "CIDR for AzureFirewallSubnet. Subnet name is fixed by Azure."
  type        = string
  default     = "10.10.0.0/26"
}

variable "bastion_subnet_prefix" {
  description = "CIDR for AzureBastionSubnet. Subnet name is fixed by Azure. Minimum /26."
  type        = string
  default     = "10.10.0.64/26"
}

variable "apim_subnet_prefix" {
  description = "CIDR for the APIM Standard v2 delegated subnet. Delegation is applied here so peering can be established before the workload apply."
  type        = string
  default     = "10.10.1.0/27"
}

variable "private_endpoint_subnet_prefix" {
  description = "CIDR for private endpoints of Foundry, APIM, and Key Vault. Sized generously to leave headroom for future PEs."
  type        = string
  default     = "10.10.2.0/26"
}

# ============================================================================
# Firewall egress allowlist
# ============================================================================

variable "provider_fqdn_allowlist" {
  description = "FQDNs the hub Firewall is allowed to reach on HTTPS. Only external model providers should appear here — Foundry-hosted models are reached via private endpoint and do not egress through Firewall."
  type        = list(string)
  default = [
    "generativelanguage.googleapis.com",
    "api.groq.com"
  ]
}

# ============================================================================
# H-series Azure Policy — allowlist inputs
# ============================================================================

variable "approved_model_publishers" {
  description = <<-EOT
    Publishers whose Foundry models the H1 built-in policy permits on
    accounts in scope. Populates the `allowedPublishers` parameter of the
    built-in policy `Foundry model deployments should only use approved
    models`. Default is `Microsoft` (covers gpt-4.1 and other Azure
    OpenAI models). Add `OpenAI`, `Meta`, `Mistral`, etc. as your catalog
    grows.
  EOT
  type        = list(string)
  default     = ["Microsoft"]
}

variable "approved_model_asset_ids" {
  description = <<-EOT
    Model asset ids the H1 built-in policy permits, in addition to
    publisher-level allow. Partial ids match by `contains`. Empty list
    means "no per-asset override" — H1 falls back to
    `approved_model_publishers`. Use this to pin specific model
    versions (for example: `azureml://registries/azureml/models/gpt-4.1`).
  EOT
  type        = list(string)
  default     = []
}

variable "approved_deployment_skus" {
  description = "Deployment SKUs H2 permits on Foundry deployments in the hub. Blocks PTU/Batch/DeveloperTier by omission. Follows the shape from https://learn.microsoft.com/azure/foundry/foundry-models/concepts/deployment-types#restrict-deployment-types-with-azure-policy"
  type        = list(string)
  default = [
    "GlobalStandard",
    "DataZoneStandard"
  ]
}

variable "policy_effect_hub" {
  description = "Effect used for the H-series policies. Ships as Deny in this sample so the guardrail is visibly enforced; landing zones typically stage as Audit first."
  type        = string
  default     = "Deny"
  validation {
    condition     = contains(["Deny", "Audit", "Disabled"], var.policy_effect_hub)
    error_message = "policy_effect_hub must be one of Deny, Audit, or Disabled."
  }
}

# ============================================================================
# Log Analytics
# ============================================================================

variable "law_retention_in_days" {
  description = "Retention on the platform Log Analytics workspace. 30 is sufficient for demo; production tenants typically keep 90+."
  type        = number
  default     = 30
}
