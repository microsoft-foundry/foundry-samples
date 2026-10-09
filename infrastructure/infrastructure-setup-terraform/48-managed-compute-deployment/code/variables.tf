variable "subscription_id" {
  description = "Azure subscription ID containing the existing Microsoft Foundry account."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a UUID."
  }
}

variable "resource_group_name" {
  description = "Resource group containing the existing Microsoft Foundry account."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.resource_group_name)) > 0
    error_message = "resource_group_name cannot be empty."
  }
}

variable "foundry_account_name" {
  description = "Name of the existing Microsoft Foundry account. The account must use kind AIServices."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$", var.foundry_account_name))
    error_message = "foundry_account_name must be 2-64 characters and contain only letters, numbers, periods, underscores, and hyphens."
  }
}

variable "deployment_name_prefix" {
  description = "Prefix for the managed-compute deployment name. Terraform appends a persistent six-character alphanumeric suffix."
  type        = string
  default     = "gemma-4-31b-it-a100"
  nullable    = false

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,56}$", var.deployment_name_prefix))
    error_message = "deployment_name_prefix must be 1-57 characters and contain only letters, numbers, periods, underscores, and hyphens."
  }
}

variable "model_id" {
  description = "Microsoft Foundry catalog model asset ID."
  type        = string
  default     = "azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5"
  nullable    = false

  validation {
    condition     = length(trimspace(var.model_id)) > 0
    error_message = "model_id cannot be empty."
  }
}

variable "deployment_template_id" {
  description = "Microsoft Foundry catalog deployment-template asset ID."
  type        = string
  default     = "azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest"
  nullable    = false

  validation {
    condition     = length(trimspace(var.deployment_template_id)) > 0
    error_message = "deployment_template_id cannot be empty."
  }
}

variable "accelerator_type" {
  description = "Managed-compute accelerator family for the selected example template."
  type        = string
  default     = "A100_80GB"
  nullable    = false

  validation {
    condition     = var.accelerator_type == "A100_80GB"
    error_message = "accelerator_type must be A100_80GB for this sample."
  }
}

variable "capacity" {
  description = "Number of model instances. The selected example template uses one accelerator per instance."
  type        = number
  default     = 1
  nullable    = false

  validation {
    condition     = var.capacity >= 1 && floor(var.capacity) == var.capacity
    error_message = "capacity must be a positive whole number."
  }
}

variable "version_upgrade_option" {
  description = "Deployment-template version upgrade policy."
  type        = string
  default     = "OnceNewDefaultVersionAvailable"
  nullable    = false

  validation {
    condition = contains(
      [
        "NoAutoUpgrade",
        "OnceCurrentVersionExpired",
        "OnceNewDefaultVersionAvailable"
      ],
      var.version_upgrade_option
    )
    error_message = "version_upgrade_option must be NoAutoUpgrade, OnceCurrentVersionExpired, or OnceNewDefaultVersionAvailable."
  }
}
