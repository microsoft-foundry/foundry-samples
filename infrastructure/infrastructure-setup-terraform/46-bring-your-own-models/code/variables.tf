# ============================================================================
# Subscription and location inputs
# ============================================================================

variable "platform_subscription_id" {
  description = "Subscription ID for Sub A (Platform, administrator-owned). Hosts the Foundry model account, APIM, Key Vault, and Log Analytics."
  type        = string
}

variable "development_subscription_id" {
  description = "Subscription ID for Sub B (Development, developer-facing). Hosts the Foundry agent account and governed projects."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant ID for both subscriptions. The azapi provider doesn't auto-detect tenant from the subscription like azurerm does, so it must be supplied explicitly."
  type        = string
}

variable "location" {
  description = "Azure region for all resources in both subscriptions."
  type        = string
  default     = "eastus"

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
  description = "Prefix for resource names. Kept short because APIM, Key Vault, and Foundry account names have length limits."
  type        = string
  default     = "contoso-byom"
}

# ============================================================================
# Foundry model backend (Sub A)
# ============================================================================

variable "foundry_model_name" {
  description = "OpenAI model deployed on the Foundry model account in Sub A. Also the alias exposed through the gateway."
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
# Non-Microsoft model providers (Sub A → Key Vault, referenced by APIM)
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
  description = "Model alias for Gemini as exposed through the gateway (visible to developers as <connection>/<alias>)."
  type        = string
  default     = "gemini-flash"
}

variable "groq_api_key" {
  description = "Groq API key. Stored in Key Vault; APIM retrieves it through an APIM named value. Never commit real values to source control."
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
# APIM (Sub A)
# ============================================================================

variable "apim_sku" {
  description = "APIM SKU. BasicV2_1 provides full policy support (including llm-token-limit) at moderate cost."
  type        = string
  default     = "BasicV2_1"
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
  description = "Token quota per project per minute enforced by the llm-token-limit policy. Default 167 tokens/min ≈ 10K tokens/hour, chosen so a demo can visibly trip the quota."
  type        = number
  default     = 167
}

variable "inference_api_version" {
  description = "Inference API version the Foundry ApiManagement connection sends to the gateway."
  type        = string
  default     = "2024-10-21"
}

# ============================================================================
# Developer RBAC (Sub B)
# ============================================================================

variable "developer_group_object_id" {
  description = "Object ID of an Entra group whose members are Contoso agent developers. Members receive the developer role on each governed project."
  type        = string
}

variable "developer_role_definition_id" {
  description = "GUID of the built-in role granted to the developer group on each project. Default 53ca6127-db72-4b80-b1b0-d745d6d5456d is the Foundry-native user role (currently named 'Foundry User'; previously 'Azure AI User' — same GUID). It grants dataAction access on the project (use models, author/run agents, threads, evaluations) with no deployment rights on the parent account. Using the GUID rather than the display name keeps this sample robust to future role renames."
  type        = string
  default     = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
}
