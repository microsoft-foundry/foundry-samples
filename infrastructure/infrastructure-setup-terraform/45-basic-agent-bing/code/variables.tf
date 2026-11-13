variable "location" {
  description = "Choose a supported Azure region for the resource group and supporting resources."
  type        = string

  validation {
    condition = contains([
      "australiaeast", "brazilsouth", "canadacentral", "canadaeast",
      "centralindia", "centralus", "eastasia", "eastus",
      "francecentral", "germanywestcentral", "italynorth", "japaneast",
      "koreacentral", "northcentralus", "northeurope", "norwayeast",
      "qatarcentral", "southafricanorth", "southcentralus", "southindia",
      "southeastasia", "spaincentral", "swedencentral", "switzerlandnorth",
      "uaenorth", "uksouth", "westeurope", "westus",
    ], var.location)
    error_message = "Choose a supported Azure region from the list above."
  }
}

variable "ai_services_name" {
  description = "Prefix for AI Foundry account name"
  type        = string
  default     = "aiServices"
}

variable "project_name" {
  description = "The name of the project"
  type        = string
  default     = "project"
}

variable "project_description" {
  description = "Description for the project"
  type        = string
  default     = "some description"
}

variable "project_display_name" {
  description = "Display name for the project"
  type        = string
  default     = "project_display_name"
}

variable "model_name" {
  description = "The model to deploy"
  type        = string
  default     = "gpt-4.1"
}

variable "model_format" {
  description = "The model format"
  type        = string
  default     = "OpenAI"
}

variable "model_version" {
  description = "The version of the model"
  type        = string
  default     = "2025-04-14"
}

variable "model_sku_name" {
  description = "The SKU name for the model deployment"
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "The capacity (quota) for the model deployment"
  type        = number
  default     = 30
}
