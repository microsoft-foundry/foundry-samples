variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "swedencentral"
}

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account"
  type        = string
  default     = "foundry-cmk-uai"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = null # Will default to {ai_foundry_name}-proj
}

variable "create_user_assigned_identity" {
  description = "Whether to create a new User-Assigned Identity or use existing"
  type        = bool
  default     = true
}

variable "user_assigned_identity_name" {
  description = "Name of the User-Assigned Identity"
  type        = string
  default     = "foundry-cmk-uai"
}

variable "user_assigned_identity_resource_group" {
  description = "Resource group of existing UAI (if not creating new)"
  type        = string
  default     = ""
}


