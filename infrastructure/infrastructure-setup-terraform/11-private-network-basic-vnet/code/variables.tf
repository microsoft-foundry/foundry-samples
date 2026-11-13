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

## As of 6/2025 the agent subnet is limited to RFC1918 Class B and Class C address space
variable "virtual_network_address_space" {
  description = "The address space for the virtual network"
  type        = string
  default     = "192.168.0.0/16"
}

variable "agent_subnet_address_prefix" {
  description = "The address prefix for the subnet that will be delegated to the Standard Agent"
  type        = string
  default     = "192.168.0.0/24"
}

variable "private_endpoint_subnet_address_prefix" {
  description = "The address prefix for the subnet that contains the private endpoints"
  type        = string
  default     = "192.168.1.0/24"
}

variable "location" {
  description = "The name of the location to provision the resources to"
  type        = string

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

variable "resource_group_name" {
  description = "Optional name for the resource group. If not specified, a name will be generated."
  type        = string
  default     = ""
}

variable "enable_container_registry" {
  description = "Enable Azure Container Registry with Private Endpoint"
  type        = bool
  default     = false
}

variable "developer_ip_cidr" {
  description = "Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26). When empty, public access remains disabled."
  type        = string
  default     = ""
}

variable "model_name" {
  description = "The name of the model to deploy"
  type        = string
  default     = "gpt-4o"
}

variable "model_version" {
  description = "The version of the model to deploy"
  type        = string
  default     = "2024-11-20"
}

variable "model_sku_name" {
  description = "The SKU name for the model deployment"
  type        = string
  default     = "GlobalStandard"
}

variable "model_capacity" {
  description = "The capacity (TPM) for the model deployment"
  type        = number
  default     = 1
}
