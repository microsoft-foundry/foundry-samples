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
  default     = "foundry-uai"
}

variable "ai_project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = null # Will default to {ai_foundry_name}-proj
}

variable "create_user_assigned_identity" {
  description = "Whether to create a new User-Assigned Identity (true) or use an existing one (false)"
  type        = bool
  default     = true
}

variable "user_assigned_identity_name" {
  description = "The name of the User-Assigned Identity (for new or existing)"
  type        = string
  default     = "foundry-uai"
}

variable "user_assigned_identity_resource_group" {
  description = "The resource group of an existing User-Assigned Identity (only used if create_user_assigned_identity=false)"
  type        = string
  default     = null
}

variable "log_analytics_workspace_name" {
  description = "The name of the Log Analytics workspace used by Application Insights. Defaults to {ai_foundry_name}-law"
  type        = string
  default     = null
}

variable "application_insights_name" {
  description = "The name of the Application Insights component connected to the project. Defaults to {ai_foundry_name}-appi"
  type        = string
  default     = null
}

variable "application_insights_connection_name" {
  description = "The name of the Application Insights connection on the project. Defaults to {application_insights_name}-connection"
  type        = string
  default     = null
}

variable "use_project_managed_identity_for_trace_ingestion" {
  description = "Use the project managed identity for trace ingestion. This authentication mode is currently in preview"
  type        = bool
  default     = false
}

variable "is_application_insights_connection_shared_to_all" {
  description = "Share an API-key Application Insights connection with all project users. Project-managed-identity connections remain project-scoped"
  type        = bool
  default     = true
}

variable "deploy_model" {
  description = "Whether to deploy the model"
  type        = bool
  default     = false
}

variable "model_name" {
  description = "The model to deploy"
  type        = string
  default     = "gpt-4o"
}

variable "model_version" {
  description = "The version of the model"
  type        = string
  default     = "2024-08-06"
}

variable "model_capacity" {
  description = "The capacity (quota) for the model deployment"
  type        = number
  default     = 1
}
