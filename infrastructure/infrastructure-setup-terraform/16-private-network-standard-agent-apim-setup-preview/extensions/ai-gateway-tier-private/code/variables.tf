# ============================================================================
# Subscription, region, naming
# ============================================================================

variable "subscription_id" {
  description = "Subscription for every resource in this sample."
  type        = string
}

variable "location" {
  description = "Single region for every resource: the gateway's integration subnet must be in the gateway's region. Use a region where AI Gateway, the model, and AI Search capacity are available; eastus2 and swedencentral are verified."
  type        = string
  default     = "swedencentral"
}

variable "name_prefix" {
  description = "Short prefix for generated names. A random suffix is appended."
  type        = string
  default     = "aigwpriv"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.name_prefix))
    error_message = "name_prefix must be 3-12 lowercase letters or numbers and start with a letter."
  }
}

# ============================================================================
# Networking (RFC1918 Class B / C address space for the agent subnet)
# ============================================================================

variable "virtual_network_address_space" {
  description = "Address space of the virtual network."
  type        = string
  default     = "192.168.0.0/16"
}

variable "agent_subnet_address_prefix" {
  description = "Subnet delegated to the Standard Agent (Microsoft.App/environments)."
  type        = string
  default     = "192.168.0.0/24"
}

variable "private_endpoint_subnet_address_prefix" {
  description = "Subnet for private endpoints (Foundry accounts, Storage, Cosmos DB, AI Search)."
  type        = string
  default     = "192.168.1.0/24"
}

variable "gateway_subnet_address_prefix" {
  description = "Subnet dedicated to the AI Gateway's outbound (private) routing. /27 minimum, /24 recommended. Delegated to Microsoft.App/environments; can't be changed after the gateway is created."
  type        = string
  default     = "192.168.2.0/24"
}

variable "foundry_allowed_ip_ranges" {
  description = "Testing convenience: public IPv4 addresses/CIDRs (for example your client egress IP) allowed to reach the agent's Foundry account, so you can run the agent script without a jumpbox. Empty (default) keeps the account fully private."
  type        = list(string)
  default     = []
  nullable    = false
}

variable "foundry_public_network_access_enabled" {
  description = "Testing convenience: open the agent's Foundry account to all networks (Entra ID auth still required). Use when foundry_allowed_ip_ranges doesn't match the source IP the Agents API sees (common from Azure-hosted machines). The model path stays private either way."
  type        = bool
  default     = false
}

# ============================================================================
# Model behind the gateway (on the private hub account)
# ============================================================================

variable "model_name" {
  description = "Model deployed on the private hub account and published through the gateway."
  type        = string
  default     = "gpt-5.4"
}

variable "model_version" {
  description = "Model version. Check availability with: az cognitiveservices model list -l <location>."
  type        = string
  default     = "2026-03-05"
}

variable "model_sku_name" {
  description = "Deployment SKU."
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "Deployment capacity in thousands of tokens per minute."
  type        = number
  default     = 1
}

# ============================================================================
# AI Gateway + connection
# ============================================================================

variable "tokens_per_minute" {
  description = "Token limit per caller identity per minute. Low by default so a burst visibly returns HTTP 429."
  type        = number
  default     = 100
}

variable "connection_name" {
  description = "Connection name. Agents reference the model as <connection_name>/<model_name>."
  type        = string
  default     = "ai-gateway"
}

variable "credential_version" {
  description = "Bump after rotating the gateway key to recreate the connection with the new key."
  type        = string
  default     = "1"
}

variable "assign_foundry_user_role" {
  description = "Grant the gateway's identity Foundry User on the private hub account. Needs role-assignment rights; set false if an administrator grants it separately. (The foundation's own data-store role assignments always need these rights.)"
  type        = bool
  default     = true
}

variable "auth_header_name" {
  description = "Header the connection uses to send the gateway key. Authorization (Bearer format) is the form the AI Gateway migration guide documents; never also send api-key (the gateway returns 400 when both are present)."
  type        = string
  default     = "Authorization"
}

variable "auth_header_format" {
  description = "Header value template; {api_key} is replaced with the gateway key."
  type        = string
  default     = "Bearer {api_key}"
}
