variable "subscription_id" {
  description = "Subscription to assign the policies in."
  type        = string
}

variable "resource_group_name" {
  description = "Optional. Resource group in the subscription to scope the assignments to. null = whole subscription."
  type        = string
  default     = null
}

variable "assignment_prefix" {
  description = "Prefix for assignment names (<prefix>-<control>)."
  type        = string
  default     = "fg"

  validation {
    condition     = length(var.assignment_prefix) >= 1 && length(var.assignment_prefix) <= 10
    error_message = "assignment_prefix must be 1-10 characters."
  }
}

variable "display_name_prefix" {
  description = "Prefix for assignment display names. Foundry shows the display name when a request is blocked."
  type        = string
  default     = "Foundry governance"
}

variable "enforce" {
  description = "true enforces the effects. false = DoNotEnforce: evaluate and report compliance without blocking."
  type        = bool
  default     = true
}

variable "not_scopes" {
  description = "Resource IDs inside the scope to exclude."
  type        = list(string)
  default     = []
}

variable "agents" {
  description = "Agent kind and hosted-agent container image controls. Empty list = policy not assigned."
  type = object({
    effect                   = optional(string, "Audit")
    allowed_agent_kinds      = optional(list(string), [])
    denied_agent_kinds       = optional(list(string), [])
    allowed_container_images = optional(list(string), [])
    denied_container_images  = optional(list(string), [])
  })
  default = {}

  validation {
    condition     = contains(["Audit", "Deny", "Disabled"], var.agents.effect)
    error_message = "agents.effect must be Audit, Deny or Disabled."
  }
}

variable "models" {
  description = "Model deployment controls. Approved-models policy is assigned if publishers or asset IDs are set; eligibility if either flag is true."
  type = object({
    effect                       = optional(string, "Audit")
    allowed_publishers           = optional(list(string), [])
    allowed_asset_ids            = optional(list(string), [])
    deny_preview_models          = optional(bool, false)
    only_allow_direct_from_azure = optional(bool, false)
  })
  default = {}

  validation {
    condition     = contains(["Audit", "Deny", "Disabled"], var.models.effect)
    error_message = "models.effect must be Audit, Deny or Disabled."
  }
}

variable "tools" {
  description = "Tool controls for agents and toolboxes. Adding \"mcp\" to approved_tool_types approves every MCP server."
  type = object({
    effect                  = optional(string, "Audit")
    approved_tool_types     = optional(list(string), [])
    approved_mcp_endpoints  = optional(list(string), [])
    approved_mcp_connectors = optional(list(string), [])
    denied_tool_types       = optional(list(string), [])
    denied_mcp_endpoints    = optional(list(string), [])
    denied_mcp_connectors   = optional(list(string), [])
  })
  default = {}

  validation {
    condition     = contains(["Audit", "Deny", "Disabled"], var.tools.effect)
    error_message = "tools.effect must be Audit, Deny or Disabled."
  }
}

variable "safety" {
  description = "Agent safety (audit-only): agents keep a required prompt content filter enabled and blocking."
  type = object({
    enabled      = optional(bool, false)
    effect       = optional(string, "Audit")
    filter_name  = optional(string, "Jailbreak")
    entity_kinds = optional(list(string), ["prompt", "hosted"])
  })
  default = {}

  validation {
    condition     = contains(["Audit", "Disabled"], var.safety.effect)
    error_message = "safety.effect must be Audit or Disabled (the policy doesn't support Deny)."
  }

  validation {
    condition     = contains(["Jailbreak", "Indirect Attack", "Indirect Attack Spotlighting", "Profanity"], var.safety.filter_name)
    error_message = "safety.filter_name must be Jailbreak, Indirect Attack, Indirect Attack Spotlighting or Profanity."
  }
}
