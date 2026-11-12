variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "eastus"
}

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account"
  type        = string
  default     = "foundry-cmk"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = null # Will default to {ai_foundry_name}-proj
}

variable "model_name" {
  description = "The model to deploy"
  type        = string
  default     = "gpt-4.1-mini"
}

variable "model_version" {
  description = "The version of the model"
  type        = string
  default     = "2025-04-14"
}
