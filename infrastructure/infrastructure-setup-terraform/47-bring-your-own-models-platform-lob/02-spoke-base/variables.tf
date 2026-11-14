# ============================================================================
# Subscription and location
# ============================================================================

variable "spoke_subscription_id" {
  description = "Subscription ID for the LoB (spoke) subscription. Hosts spoke networking, App Gateway, agent Foundry account, and the S-series Azure Policy assignments."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant ID."
  type        = string
}

variable "location" {
  description = "Azure region. Must match hub-base's location (private DNS zones and peering assume same region)."
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
  description = "Prefix for spoke resource names."
  type        = string
  default     = "contoso-byom-lob"
}

variable "lob_name" {
  description = "Short LoB identifier included in resource names — supports multi-LoB deployments off the same hub."
  type        = string
  default     = "alpha"
}

# ============================================================================
# hub-base state pointer (for the forced-tunnel route table only).
# ============================================================================

variable "hub_base_state_path" {
  description = "Path to hub-base's terraform.tfstate. Consumed via terraform_remote_state so spoke-base does not read hub-base's variables."
  type        = string
  default     = "../01-hub-base/terraform.tfstate"
}

# ============================================================================
# Networking
# ============================================================================

variable "spoke_vnet_address_space" {
  description = "CIDR block for the spoke VNet. Must not overlap with the hub VNet."
  type        = list(string)
  default     = ["10.20.0.0/16"]
}

variable "appgw_subnet_prefix" {
  description = "CIDR for the App Gateway subnet."
  type        = string
  default     = "10.20.0.0/24"
}

variable "workload_subnet_prefix" {
  description = "CIDR for the workload subnet (agent runtime, capability host consumers)."
  type        = string
  default     = "10.20.1.0/24"
}

variable "private_endpoint_subnet_prefix" {
  description = "CIDR for spoke private endpoints (Foundry agent account PE)."
  type        = string
  default     = "10.20.2.0/26"
}

# ============================================================================
# Application Gateway
# ============================================================================

variable "appgw_sku" {
  description = "App Gateway SKU. WAF_v2 provides Web Application Firewall — the only public surface in the spoke has to be defended."
  type        = string
  default     = "WAF_v2"
}

variable "appgw_capacity" {
  description = "App Gateway autoscale minimum. Fixed at 2 for demo footprint; production tenants typically scale higher."
  type        = number
  default     = 2
}

# ============================================================================
# S-series policy inputs
# ============================================================================

variable "policy_effect_spoke" {
  description = "Effect used for the S-series policies. Ships as Deny per the sample's demo posture."
  type        = string
  default     = "Deny"
  validation {
    condition     = contains(["Deny", "Audit", "Disabled"], var.policy_effect_spoke)
    error_message = "policy_effect_spoke must be one of Deny, Audit, or Disabled."
  }
}

# ============================================================================
# Log Analytics
# ============================================================================

variable "law_retention_in_days" {
  description = "Retention on the LoB Log Analytics workspace. 30 is sufficient for demo."
  type        = number
  default     = 30
}
