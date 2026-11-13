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
