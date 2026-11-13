variable "foundry_location" {
  description = "Optional Foundry account location override. Defaults to the resource-group location."
  type        = string
  default     = null

  validation {
    condition = var.foundry_location == null ? true : contains([
      "australiaeast", "brazilsouth", "canadacentral", "canadaeast", "centralindia", "centralus",
      "eastasia", "eastus", "francecentral", "germanywestcentral", "italynorth", "japaneast",
      "koreacentral", "northcentralus", "northeurope", "norwayeast", "qatarcentral", "southafricanorth",
      "southcentralus", "southindia", "southeastasia", "spaincentral", "swedencentral", "switzerlandnorth",
      "uaenorth", "uksouth", "usgovarizona", "usgovvirginia", "westeurope", "westus", "westus3",
    ], var.foundry_location)
    error_message = "The location must be a supported Microsoft Foundry region."
  }
}

variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "eastus"

  validation {
    condition = contains([
      "australiaeast", "brazilsouth", "canadacentral", "canadaeast", "centralindia", "centralus",
      "eastasia", "eastus", "francecentral", "germanywestcentral", "italynorth", "japaneast",
      "koreacentral", "northcentralus", "northeurope", "norwayeast", "qatarcentral", "southafricanorth",
      "southcentralus", "southindia", "southeastasia", "spaincentral", "swedencentral", "switzerlandnorth",
      "uaenorth", "uksouth", "usgovarizona", "usgovvirginia", "westeurope", "westus", "westus3",
    ], var.location)
    error_message = "The location must be a supported Microsoft Foundry region."
  }
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
