# ============================================================================
# Subscription, regions, resource group
# ============================================================================

variable "subscription_id" {
  description = "Subscription that hosts the hub (Foundry account, model, and AI Gateway)."
  type        = string
}

variable "location" {
  description = "Region for the hub Foundry account, project, and model. Any region with model quota; it can differ from gateway_location."
  type        = string
  default     = "eastus2"
}

variable "gateway_location" {
  description = "Region for the AI Gateway. Use a region where AI Gateway is available; eastus2 and swedencentral are verified. Can differ from location."
  type        = string
  default     = "eastus2"
}

variable "existing_resource_group_name" {
  description = "Existing resource group to deploy into. Leave empty to create rg-<name_prefix>-<suffix>. An existing group isn't deleted on destroy."
  type        = string
  default     = ""
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix for generated names. A random suffix is appended."
  type        = string
  default     = "aigwhub"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.name_prefix))
    error_message = "name_prefix must be 3-12 lowercase letters or numbers and start with a letter."
  }
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}

# ============================================================================
# Hub Foundry account, project, and model
# ============================================================================

variable "project_name" {
  description = "Hub project (admin workspace) created under the account."
  type        = string
  default     = "hub-project"
}

variable "model_name" {
  description = "Model to deploy. The deployment uses the same name."
  type        = string
  default     = "gpt-5.4"
}

variable "model_version" {
  description = "Model version. Check availability with: az cognitiveservices model list -l <location>."
  type        = string
  default     = "2026-03-05"
}

variable "model_format" {
  description = "Model format."
  type        = string
  default     = "OpenAI"
}

variable "model_sku_name" {
  description = "Deployment SKU."
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "Deployment capacity in thousands of tokens per minute. 1 keeps the sample deployable on tight quota; raise it for real workloads."
  type        = number
  default     = 1
}

# ============================================================================
# AI Gateway
# ============================================================================

variable "gateway_name" {
  description = "AI Gateway name (3-24 lowercase letters, numbers, hyphens). Leave empty to use <name_prefix>-<suffix>."
  type        = string
  default     = ""
  nullable    = false
}

variable "alias_name" {
  description = "Callable model name on the gateway. Defaults to model_name."
  type        = string
  default     = null
}

variable "tokens_per_minute" {
  description = "Token limit per caller identity per minute. Low by default so a burst visibly returns HTTP 429."
  type        = number
  default     = 100
}

variable "api_key_name" {
  description = "Name of the runtime API key that spoke connections use."
  type        = string
  default     = "foundry-connection"
}

variable "purge_on_destroy" {
  description = "Purge the soft-deleted Foundry account during terraform destroy so its name and quota are released immediately."
  type        = bool
  default     = true
}

variable "assign_foundry_user_role" {
  description = "Grant the gateway's identity Foundry User on the hub account. Needs role-assignment rights (Owner, User Access Administrator, RBAC Administrator, or Foundry Account Owner). Set false if an administrator grants it separately (see the README)."
  type        = bool
  default     = true
}
