# Example: Azure OpenAI Connection
# This example shows how to create a connection from AI Foundry to a new or existing Azure OpenAI resource.
# It's the Terraform version of infrastructure-setup-bicep/01-connections/connection-azure-openai.bicep.
#
# With auth_type = "ApiKey", the account key is read at apply time and sent as a write-only value,
# so it isn't stored in Terraform state or plan files. This needs Terraform 1.11 or later.
# After you regenerate the key, send the new one with:
#   terraform apply -replace=azapi_resource.azure_openai_connection

terraform {
  required_version = ">= 1.11.0"
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
  }
}

provider "azapi" {}

variable "ai_foundry_name" {
  description = "Name of your existing AI Foundry account"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group containing the AI Foundry account and the Azure OpenAI resource"
  type        = string
}

variable "azure_openai_name" {
  description = "Name of the Azure OpenAI resource (default: aoai-<ai_foundry_name>)"
  type        = string
  default     = null
}

variable "location" {
  description = "Azure region for a new Azure OpenAI resource"
  type        = string
  default     = "westus"
}

variable "create_new_azure_openai" {
  description = "Create a new Azure OpenAI resource or use an existing one"
  type        = bool
  default     = true
}

variable "auth_type" {
  description = "Authentication type: ApiKey or AAD"
  type        = string
  default     = "ApiKey"

  validation {
    condition     = contains(["ApiKey", "AAD"], var.auth_type)
    error_message = "auth_type must be ApiKey or AAD."
  }
}

variable "is_shared_to_all" {
  description = "Share the connection with all users. The service stores true on an account-level connection, whatever value is sent."
  type        = bool
  default     = true
}

# Reference existing resources
data "azapi_client_config" "current" {}

data "azapi_resource" "rg" {
  type      = "Microsoft.Resources/resourceGroups@2021-04-01"
  name      = var.resource_group_name
  parent_id = data.azapi_client_config.current.subscription_resource_id
}

data "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = var.ai_foundry_name
  parent_id = data.azapi_resource.rg.id
}

# Conditionally create a new Azure OpenAI resource
resource "azapi_resource" "azure_openai" {
  count     = var.create_new_azure_openai ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts@2023-05-01"
  name      = local.azure_openai_name
  parent_id = data.azapi_resource.rg.id
  location  = var.location

  body = {
    kind = "OpenAI"
    sku = {
      name = "S0"
    }
    properties = {}
  }

  response_export_values = ["properties.endpoint"]
}

# Reference an existing Azure OpenAI resource
data "azapi_resource" "existing_azure_openai" {
  count                  = var.create_new_azure_openai ? 0 : 1
  type                   = "Microsoft.CognitiveServices/accounts@2023-05-01"
  name                   = local.azure_openai_name
  parent_id              = data.azapi_resource.rg.id
  response_export_values = ["properties.endpoint"]
}

locals {
  azure_openai_name     = coalesce(var.azure_openai_name, "aoai-${var.ai_foundry_name}")
  azure_openai_id       = var.create_new_azure_openai ? azapi_resource.azure_openai[0].id : data.azapi_resource.existing_azure_openai[0].id
  azure_openai_endpoint = var.create_new_azure_openai ? azapi_resource.azure_openai[0].output.properties.endpoint : data.azapi_resource.existing_azure_openai[0].output.properties.endpoint
  azure_openai_location = var.create_new_azure_openai ? azapi_resource.azure_openai[0].location : data.azapi_resource.existing_azure_openai[0].location
}

# Read the account key at apply time; ephemeral values are never stored in state
ephemeral "azapi_resource_action" "azure_openai_keys" {
  count                  = var.auth_type == "ApiKey" ? 1 : 0
  type                   = "Microsoft.CognitiveServices/accounts@2023-05-01"
  resource_id            = local.azure_openai_id
  action                 = "listKeys"
  method                 = "POST"
  response_export_values = ["key1"]
}

# Create Azure OpenAI connection
resource "azapi_resource" "azure_openai_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = "${var.ai_foundry_name}-openai"
  parent_id                 = data.azapi_resource.ai_foundry.id
  schema_validation_enabled = false # the provider's schema limits names to 33 characters; the service accepts longer ones

  body = {
    properties = {
      category      = "AzureOpenAI"
      target        = local.azure_openai_endpoint
      authType      = var.auth_type
      isSharedToAll = var.is_shared_to_all
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.azure_openai_id
        location   = local.azure_openai_location
      }
    }
  }

  # Write-only: merged into the request body on create and update, never stored in state or plan files
  sensitive_body = var.auth_type == "ApiKey" ? {
    properties = {
      credentials = {
        key = ephemeral.azapi_resource_action.azure_openai_keys[0].output.key1
      }
    }
  } : null

  lifecycle {
    # The service stores isSharedToAll = true on an account-level connection, whatever value is sent
    ignore_changes = [body.properties.isSharedToAll]
  }
}

output "connection_id" {
  value = azapi_resource.azure_openai_connection.id
}
