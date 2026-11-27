# ============================================================================
# Gateway
# ============================================================================

variable "name" {
  description = "AI Gateway name. Becomes the first label of the runtime host name (<name>.<region-stamp>.ai.gateway.azure.com)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,22}[a-z0-9]$", var.name))
    error_message = "name must be 3-24 characters: lowercase letters, numbers, and hyphens, starting and ending with a letter or number."
  }
}

variable "location" {
  description = "Region for the AI Gateway. Use a region where AI Gateway is available (az provider show -n Microsoft.ApiManagement --query \"resourceTypes[?resourceType=='aigateways'].locations\"); eastus2 and swedencentral are verified."
  type        = string
}

variable "resource_group_id" {
  description = "Resource ID of the resource group that holds the gateway."
  type        = string
}

variable "tags" {
  description = "Tags applied to the gateway."
  type        = map(string)
  default     = {}
}

variable "backend_subnet_id" {
  description = "Optional subnet for outbound (private) routing. Must be in the gateway's region, delegated to Microsoft.App/environments, dedicated to this gateway, and have an NSG allowing outbound TCP 443 to the Storage and AzureKeyVault service tags. Leave null for a public-routing gateway."
  type        = string
  default     = null
}

# ============================================================================
# Backend Foundry model
# ============================================================================

variable "foundry_account_id" {
  description = "Resource ID of the Foundry (AIServices) account that hosts the model deployment. The gateway's managed identity gets Foundry User on it."
  type        = string
}

variable "foundry_account_endpoint" {
  description = "The account's properties.endpoint (https://<account>.cognitiveservices.azure.com/)."
  type        = string
}

variable "model_deployment_id" {
  description = "Resource ID of the model deployment (.../accounts/<account>/deployments/<name>)."
  type        = string
}

variable "model_deployment_name" {
  description = "Name of the model deployment. Also used as the gateway model registration name."
  type        = string
}

variable "model_version" {
  description = "Version of the deployed model."
  type        = string
}

# ============================================================================
# Gateway configuration
# ============================================================================

variable "provider_name" {
  description = "Name of the Foundry model provider created in the gateway's default workspace."
  type        = string
  default     = "foundry"
}

variable "alias_name" {
  description = "Callable alias that clients (and the Foundry connection) send in the request \"model\" field. Defaults to the deployment name."
  type        = string
  default     = null
}

variable "tokens_per_minute" {
  description = "Token limit per caller identity, per minute, enforced on the model. Low by default so a short burst visibly returns HTTP 429."
  type        = number
  default     = 100

  validation {
    condition     = var.tokens_per_minute >= 1
    error_message = "tokens_per_minute must be at least 1."
  }
}

variable "api_key_name" {
  description = "Name of the runtime API key created for the Foundry connection."
  type        = string
  default     = "foundry-connection"
}

variable "assign_foundry_user_role" {
  description = "Grant the gateway's managed identity Foundry User on the backend account. Requires Microsoft.Authorization/roleAssignments/write (Owner, User Access Administrator, RBAC Administrator, or Foundry Account Owner). Set false if an administrator grants it out of band; the provider then waits rbac_propagation_wait for that grant."
  type        = bool
  default     = true
}

variable "rbac_propagation_wait" {
  description = "How long to wait after granting the gateway identity Foundry User before registering the provider."
  type        = string
  default     = "60s"
}
