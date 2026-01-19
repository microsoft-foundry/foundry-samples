variable "subscription_id" {
  description = "The Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "The name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "uaenorth"
}

variable "foundry_identifier" {
  description = "Unique identifier for the AI Foundry account name (change this to recreate the foundry account)"
  type        = string
  default     = "foundry"
}

# Feature flags for optional resources
variable "enable_networking" {
  description = "Enable VNet, subnets, and network infrastructure"
  type        = bool
  default     = false
}

variable "enable_storage" {
  description = "Enable Storage Account and its private endpoints"
  type        = bool
  default     = false
}

variable "enable_aisearch" {
  description = "Enable AI Search Service and its private endpoint"
  type        = bool
  default     = false
}

variable "enable_cosmos" {
  description = "Enable Cosmos DB Account and its private endpoint"
  type        = bool
  default     = false
}

variable "enable_dns" {
  description = "Enable Private DNS Zones and VNet links"
  type        = bool
  default     = false
}

variable "vnet_name" {
  description = "Name of the virtual network"
  type        = string
  default     = "vnet-aifoundry"
}

variable "vnet_address_prefix" {
  description = "Address prefix for the virtual network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_endpoints_subnet_name" {
  description = "Name of the private endpoints subnet"
  type        = string
  default     = "snet-privateendpoints"
}

variable "private_endpoints_subnet_prefix" {
  description = "Address prefix for private endpoints subnet"
  type        = string
  default     = "10.0.1.0/24"
}
