variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "eastus"
}

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account (must be globally unique)"
  type        = string
  default     = "foundry-disable-localauth"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = null # Will default to {ai_foundry_name}-proj
}

variable "model_deployment_name" {
  description = "The name of the model deployment"
  type        = string
  default     = "gpt-4.1-mini"
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

variable "model_capacity" {
  description = "The capacity (quota) for the model deployment"
  type        = number
  default     = 1
}
