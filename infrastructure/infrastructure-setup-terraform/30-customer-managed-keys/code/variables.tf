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
