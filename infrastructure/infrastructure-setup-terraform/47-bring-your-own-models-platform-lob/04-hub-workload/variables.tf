# ============================================================================
# Subscription and location — must match hub-base
# ============================================================================

variable "platform_subscription_id" {
  description = "Same as hub-base's platform_subscription_id."
  type        = string
}

variable "tenant_id" {
  description = "Same as hub-base's tenant_id."
  type        = string
}

variable "foundry_location" {
  description = "Optional Foundry account location override. Defaults to the hub resource-group location."
  type        = string
  default     = null

  validation {
    condition = var.foundry_location == null ? true : contains([
      "australiaeast", "brazilsouth", "canadacentral", "canadaeast", "centralindia", "centralus",
      "eastasia", "eastus", "francecentral", "germanywestcentral", "italynorth", "japaneast",
      "koreacentral", "northcentralus", "northeurope", "norwayeast", "qatarcentral", "southafricanorth",
      "southcentralus", "southindia", "southeastasia", "spaincentral", "swedencentral", "switzerlandnorth",
      "uaenorth", "uksouth", "usgovarizona", "usgovvirginia", "westeurope", "westus", "westus3",
    ], var.foundry_location)
    error_message = "The location must be a supported Microsoft Foundry region."
  }
}

variable "name_prefix" {
  description = "Same as hub-base's name_prefix. Used for names of workload resources placed alongside hub-base's resources."
  type        = string
  default     = "contoso-byom"
}

# ============================================================================
# hub-base state pointer (terraform_remote_state)
# ============================================================================

variable "hub_base_state_path" {
  description = "Path to hub-base's terraform.tfstate. Consumed via terraform_remote_state so hub-workload does not read hub-base's variables — only its published outputs."
  type        = string
  default     = "../01-hub-base/terraform.tfstate"
}

# ============================================================================
# Foundry model backend
# ============================================================================

variable "foundry_model_name" {
  description = "OpenAI model deployed on the Foundry model account. Also the alias exposed through the gateway."
  type        = string
  default     = "gpt-4.1"
}

variable "foundry_model_version" {
  description = "Version of the Foundry model deployment."
  type        = string
  default     = "2025-04-14"
}

variable "foundry_model_capacity" {
  description = "Capacity for the Foundry model deployment (thousands of tokens per minute)."
  type        = number
  default     = 40
}

# ============================================================================
# Non-Microsoft model providers → Key Vault → APIM named values
# ============================================================================

variable "gemini_api_key" {
  description = "Google AI Studio API key. Stored in Key Vault; APIM retrieves it through an APIM named value. Never commit real values to source control."
  type        = string
  sensitive   = true
}

variable "gemini_model_name" {
  description = "Gemini model name sent to Google's OpenAI-compatible endpoint."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "gemini_alias" {
  description = "Model alias for Gemini as exposed through the gateway."
  type        = string
  default     = "gemini-flash"
}

variable "groq_api_key" {
  description = "Groq API key. Stored in Key Vault; APIM retrieves it through an APIM named value."
  type        = string
  sensitive   = true
}

variable "groq_model_name" {
  description = "Groq model name sent to Groq's OpenAI-compatible endpoint."
  type        = string
  default     = "llama-3.3-70b-versatile"
}

variable "groq_alias" {
  description = "Model alias for Groq's Llama model as exposed through the gateway."
  type        = string
  default     = "llama-3-70b"
}

# ============================================================================
# APIM
# ============================================================================

variable "apim_sku" {
  description = "APIM SKU. StandardV2_1 is required for VNet integration + private endpoint. See ../README.md § SKU and cost implications."
  type        = string
  default     = "StandardV2_1"
}

variable "apim_publisher_name" {
  description = "APIM publisher organization name (required by APIM at create time)."
  type        = string
  default     = "Contoso Platform Team"
}

variable "apim_publisher_email" {
  description = "APIM publisher email (required by APIM at create time)."
  type        = string
}

variable "quota_tokens_per_minute" {
  description = "Token quota per project per minute — published in outputs so hub-allowlist renders the same value into the APIM policy."
  type        = number
  default     = 167
}

variable "inference_api_version" {
  description = "Inference API version the Foundry ApiManagement connection sends to the gateway."
  type        = string
  default     = "2024-10-21"
}

# ============================================================================
# Contract publication
# ============================================================================

variable "contract_output_path" {
  description = "Path (relative to hub-workload/) where the published contract JSON is written."
  type        = string
  default     = "../contracts/hub-workload.contract.json"
}
