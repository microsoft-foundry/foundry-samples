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

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "allowed_public_ips" {
  description = "List of public IP addresses (CIDR format) allowed to access Key Vault"
  type        = list(string)
  default     = []
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

variable "enable_vm" {
  description = "Enable Windows VM and Azure Bastion"
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

variable "vm_subnet_name" {
  description = "Name of the VM subnet"
  type        = string
  default     = "snet-vms"
}

variable "vm_subnet_prefix" {
  description = "Address prefix for VM subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "bastion_subnet_prefix" {
  description = "Address prefix for Azure Bastion subnet"
  type        = string
  default     = "10.0.3.0/26"
}

variable "bastion_name" {
  description = "Name of Azure Bastion"
  type        = string
  default     = "bastion-aifoundry"
}

variable "vm_name" {
  description = "Name of the virtual machine"
  type        = string
  default     = "vm-win2025"
}

variable "vm_admin_username" {
  description = "Admin username for the VM"
  type        = string
  sensitive   = true
}
