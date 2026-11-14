variable "location" {
  description = "The name of the location to provision the resources to"
  type        = string

  validation {
    condition = contains([
      "australiaeast",
      "brazilsouth",
      "canadacentral",
      "canadaeast",
      "centralindia",
      "centralus",
      "eastasia",
      "eastus",
      "francecentral",
      "germanywestcentral",
      "italynorth",
      "japaneast",
      "koreacentral",
      "northcentralus",
      "northeurope",
      "norwayeast",
      "qatarcentral",
      "southafricanorth",
      "southcentralus",
      "southindia",
      "southeastasia",
      "spaincentral",
      "swedencentral",
      "switzerlandnorth",
      "uaenorth",
      "uksouth",
      "usgovarizona",
      "usgovvirginia",
      "westeurope",
      "westus",
      "westus3",
    ], var.location)
    error_message = "The location must be a supported Microsoft Foundry region."
  }
}

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

variable "subscription_id" {
  type = string
}