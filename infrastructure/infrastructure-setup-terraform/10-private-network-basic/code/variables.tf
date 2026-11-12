variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "westus3"
}

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account"
  type        = string
  default     = "foundrypnadisabled"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = null # Will default to {ai_foundry_name}-proj
}

variable "virtual_network_name" {
  description = "The name of the virtual network"
  type        = string
  default     = "private-vnet"
}

variable "virtual_network_address_space" {
  description = "The address space for the virtual network"
  type        = string
  default     = "192.168.0.0/16"
}

variable "pe_subnet_name" {
  description = "The name of the private endpoint subnet"
  type        = string
  default     = "pe-subnet"
}

variable "pe_subnet_address_prefix" {
  description = "The address prefix for the private endpoint subnet"
  type        = string
  default     = "192.168.0.0/24"
}

variable "model_name" {
  description = "The model to deploy"
  type        = string
  default     = "gpt-4o"
}

variable "model_version" {
  description = "The version of the model"
  type        = string
  default     = "2024-08-06"
}
