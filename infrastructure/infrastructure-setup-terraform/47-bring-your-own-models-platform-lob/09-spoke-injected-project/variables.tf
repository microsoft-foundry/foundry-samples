variable "spoke_subscription_id" {
  description = "Spoke (LoB) subscription id. Same as 02-spoke-base's spoke_subscription_id."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant. Must match hub-workload's tenant_id."
  type        = string
}

variable "name_prefix" {
  description = "Same as spoke-base's name_prefix. Used to derive resource names."
  type        = string
  default     = "foundrysample-byom-lob"
}

variable "spoke_base_state_path" {
  description = "Path to 02-spoke-base's terraform.tfstate (spoke VNet, PE subnet, RG)."
  type        = string
  default     = "../02-spoke-base/terraform.tfstate"
}

variable "hub_base_state_path" {
  description = "Path to 01-hub-base's terraform.tfstate. Provides hub-owned Foundry private DNS zone IDs so the injected account PE can register A records cross-subscription."
  type        = string
  default     = "../01-hub-base/terraform.tfstate"
}

variable "contract_path" {
  description = "Path to the platform contract file published by hub-workload. Read once at plan time; never modified."
  type        = string
  default     = "../contracts/hub-workload.contract.json"
}

variable "project_name" {
  description = "Foundry project name (lower-case, no spaces). Kept distinct from the non-injected sample-47 project so both can coexist for A/B latency comparison."
  type        = string
  default     = "hrbotdp"
}

variable "project_display_name" {
  description = "Foundry project display name shown in the portal."
  type        = string
  default     = "HR Bot (data-proxy)"
}

variable "project_description" {
  description = "Foundry project description."
  type        = string
  default     = "VNet-injected LoB project. Exercises the Foundry data-proxy on the projects-scoped Responses -> APIM (BYOG) path for latency A/B testing."
}

# ============================================================================
# Networking
# ============================================================================

variable "agent_subnet_prefix" {
  description = "CIDR for the delegated Standard-Agent subnet added to the existing spoke VNet. Must be free within the spoke address space (10.20.0.0/16). Defaults to a /24 clear of appgw (.0.0/24), workload (.1.0/24), PE (.2.0/26), AzureBastionSubnet (.3.0/26), and snet-jumpbox (.4.0/28)."
  type        = string
  default     = "10.20.5.0/24"
}

# ============================================================================
# Model deployment (optional local model on the injected account)
# ============================================================================

# No local model deployments are created. All inference is proxied through
# the platform APIM gateway via the BYOG ApiManagement connection, so the
# data-proxy sits on the projects-scoped Responses -> APIM path.
