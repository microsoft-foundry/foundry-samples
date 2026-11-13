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
  default     = "foundry-storage"
}

variable "create_storage_account" {
  description = "Whether to create a new storage account (true) or use an existing one (false)"
  type        = bool
  default     = true
}

variable "storage_account_name" {
  description = "Name of the storage account (for new or existing)"
  type        = string
  default     = ""
}

variable "storage_account_resource_group" {
  description = "Resource group of existing storage account (only used if create_storage_account=false)"
  type        = string
  default     = ""
}
