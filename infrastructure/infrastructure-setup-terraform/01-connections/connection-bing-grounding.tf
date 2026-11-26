# Example: Grounding with Bing Search Connection
# This example shows how to create a connection from AI Foundry to a new or existing Grounding with Bing Search resource.
# It's the Terraform version of infrastructure-setup-bicep/01-connections/connection-bing-grounding.bicep.
#
# The Bicep sample takes the key as a parameter. This example reads the key from the Bing resource at
# apply time instead and sends it as a write-only value, so it isn't stored in Terraform state or plan
# files. This needs Terraform 1.11 or later. After you regenerate the key, send the new one with:
#   terraform apply -replace=azapi_resource.bing_connection

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
  description = "Resource group containing the AI Foundry account and the Bing resource"
  type        = string
}

variable "bing_resource_name" {
  description = "Name of the Grounding with Bing Search resource (default: st<ai_foundry_name>, as in the Bicep sample)"
  type        = string
  default     = null
}

variable "location" {
  description = "Azure region for a new Bing resource"
  type        = string
  default     = "global"
}

variable "create_new_bing" {
  description = "Create a new Grounding with Bing Search resource or use an existing one"
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

# Conditionally create a new Grounding with Bing Search resource
resource "azapi_resource" "bing" {
  count                     = var.create_new_bing ? 1 : 0
  type                      = "Microsoft.Bing/accounts@2020-06-10"
  name                      = local.bing_resource_name
  parent_id                 = data.azapi_resource.rg.id
  location                  = var.location
  schema_validation_enabled = false # the provider has no schema for this resource type

  body = {
    kind = "Bing.Grounding"
    sku = {
      name = "G1"
    }
    properties = {
      statisticsEnabled = false
    }
  }
}

# Reference an existing Grounding with Bing Search resource
data "azapi_resource" "existing_bing" {
  count     = var.create_new_bing ? 0 : 1
  type      = "Microsoft.Bing/accounts@2020-06-10"
  name      = local.bing_resource_name
  parent_id = data.azapi_resource.rg.id
}

locals {
  bing_resource_name = coalesce(var.bing_resource_name, "st${var.ai_foundry_name}")
  bing_id            = var.create_new_bing ? azapi_resource.bing[0].id : data.azapi_resource.existing_bing[0].id
}

# Read the Bing key at apply time; ephemeral values are never stored in state
ephemeral "azapi_resource_action" "bing_keys" {
  type                   = "Microsoft.Bing/accounts@2020-06-10"
  resource_id            = local.bing_id
  action                 = "listKeys"
  method                 = "POST"
  response_export_values = ["key1"]
}

# Create Grounding with Bing Search connection
resource "azapi_resource" "bing_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = "${var.ai_foundry_name}-bing"
  parent_id                 = data.azapi_resource.ai_foundry.id
  schema_validation_enabled = false # the provider's schema limits names to 33 characters; the service accepts longer ones

  body = {
    properties = {
      category      = "ApiKey"
      target        = "https://api.bing.microsoft.com/"
      authType      = "ApiKey"
      isSharedToAll = true
      metadata = {
        ApiType    = "Azure"
        Type       = "bing_grounding"
        ResourceId = local.bing_id
      }
    }
  }

  # Write-only: merged into the request body on create and update, never stored in state or plan files
  sensitive_body = {
    properties = {
      credentials = {
        key = ephemeral.azapi_resource_action.bing_keys.output.key1
      }
    }
  }
}

output "connection_id" {
  value = azapi_resource.bing_connection.id
}
