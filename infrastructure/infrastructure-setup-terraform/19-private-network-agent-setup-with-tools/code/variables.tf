variable "location" {
  description = "The Azure region where resources will be deployed"
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

variable "ai_services_name_prefix" {
  description = "Prefix for AI Foundry account name"
  type        = string
  default     = "aifoundry"
}

variable "project_name" {
  description = "The name of the project"
  type        = string
  default     = "hybrid-agent-project"
}

variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = list(string)
  default     = ["192.168.0.0/16"]
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

########## BYO (Bring Your Own) resource variables
########## Leave empty to create new resources. Provide resource IDs to use existing ones.

variable "existing_resource_group_name" {
  description = "Name of an existing resource group. Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_vnet_id" {
  description = "Resource ID of an existing VNet. Leave empty to create a new one. When provided, existing subnet IDs must also be provided."
  type        = string
  default     = ""
}

variable "existing_agent_subnet_id" {
  description = "Resource ID of an existing agent subnet (must be delegated to Microsoft.App/environments). Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_pe_subnet_id" {
  description = "Resource ID of an existing private endpoint subnet. Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_mcp_subnet_id" {
  description = "Resource ID of an existing MCP subnet (must be delegated to Microsoft.App/environments). Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_storage_account_id" {
  description = "Resource ID of an existing Storage Account. Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_cosmosdb_account_id" {
  description = "Resource ID of an existing Cosmos DB account. Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_ai_search_id" {
  description = "Resource ID of an existing AI Search service. Leave empty to create a new one."
  type        = string
  default     = ""
}

variable "existing_dns_zones_resource_group" {
  description = "Resource group containing existing private DNS zones. Leave empty to create new zones. When provided, all 6 zones are expected to exist in this RG."
  type        = string
  default     = ""
}

variable "existing_dns_zones_subscription_id" {
  description = "Subscription ID where existing private DNS zones are located. Leave empty to use the current subscription. Only used when existing_dns_zones_resource_group is set."
  type        = string
  default     = ""
}

variable "existing_fabric_workspace_id" {
  description = "Resource ID of an existing Fabric workspace for Data Agent private endpoint. Leave empty to skip Fabric integration."
  type        = string
  default     = ""
}

########## Optional: Azure Container Registry
########## Enable to create a Premium ACR with Private Endpoint for hosted agent containers.

variable "enable_container_registry" {
  description = "Enable Azure Container Registry with Private Endpoint for hosted agent containers"
  type        = bool
  default     = false
}

variable "developer_ip_cidr" {
  description = "Optional developer IP CIDR to allowlist for ACR push access (e.g., 203.0.113.0/26). Only used when enable_container_registry is true. When empty, public access remains disabled."
  type        = string
  default     = ""
}
