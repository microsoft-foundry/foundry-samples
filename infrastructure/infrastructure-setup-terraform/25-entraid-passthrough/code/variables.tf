variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "swedencentral"
}

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account"
  type        = string
  default     = "entraid-foundry"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = "entraid-foundry-proj"
}

variable "project_description" {
  description = "Description for the project"
  type        = string
  default     = "A project for the AI Foundry account with storage account"
}

variable "project_display_name" {
  description = "Display name for the project"
  type        = string
  default     = "project"
}

variable "storage_account_name" {
  description = "Name of the storage account"
  type        = string
  default     = "entraidfoundry"
}
