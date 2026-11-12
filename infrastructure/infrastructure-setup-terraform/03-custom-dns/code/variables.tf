variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "swedencentral"
}

variable "custom_subdomain_name" {
  description = "Custom subdomain name for the AI Foundry API endpoint (must be globally unique)"
  type        = string
  default     = "my-unique-foundry-dns"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = "custom-dns-proj"
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
