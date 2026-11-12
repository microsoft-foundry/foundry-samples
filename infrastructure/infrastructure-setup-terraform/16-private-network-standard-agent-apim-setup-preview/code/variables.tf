variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "eastus"
}

variable "ai_services_name_prefix" {
  description = "Prefix for AI Foundry account name"
  type        = string
  default     = "foundry"
}

variable "project_name" {
  description = "The name of the project"
  type        = string
  default     = "private-apim-agent-project"
}

variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "subnet_private_endpoints_prefix" {
  description = "Address prefix for private endpoints subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "subnet_apim_prefix" {
  description = "Address prefix for APIM subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "apim_sku" {
  description = "SKU for API Management (Developer, Standard, Premium)"
  type        = string
  default     = "Developer"
  validation {
    condition     = contains(["Developer", "Standard", "Premium"], var.apim_sku)
    error_message = "APIM SKU must be Developer, Standard, or Premium for VNet integration"
  }
}

variable "apim_publisher_name" {
  description = "Publisher name for API Management"
  type        = string
  default     = "AI Foundry Publisher"
}

variable "apim_publisher_email" {
  description = "Publisher email for API Management"
  type        = string
  default     = "admin@example.com"
}

variable "model_name" {
  description = "The model to deploy"
  type        = string
  default     = "gpt-4.1"
}

variable "model_version" {
  description = "The version of the model"
  type        = string
  default     = "2025-04-14"
}

variable "model_capacity" {
  description = "The capacity of the model deployment"
  type        = number
  default     = 40
}
