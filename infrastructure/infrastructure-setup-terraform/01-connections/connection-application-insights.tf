# Example: Application Insights Connection
# This example shows how to connect an existing Application Insights component to an AI Foundry
# account and project using key-based authentication, and gives the project's system-assigned
# managed identity read access so evaluation can read agent traces
# (Privileged Monitoring Data Reader is required to read GenAI content).
# Only one Application Insights connection can be set on a project at a time.

terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.5"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.37"
    }
  }
}

provider "azapi" {}
provider "azurerm" {
  features {}
}

variable "ai_foundry_name" {
  description = "Name of your existing AI Foundry account"
  type        = string
}

variable "ai_project_name" {
  description = "Name of your existing project (sub-resource of the AI Foundry account)"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group containing AI Foundry and Application Insights"
  type        = string
}

variable "application_insights_name" {
  description = "Name of the existing Application Insights component"
  type        = string
}

variable "is_shared_to_all" {
  description = "Share the connection with all users of the account or project"
  type        = bool
  default     = true
}

# Log Analytics Reader + Privileged Monitoring Data Reader
locals {
  reader_role_definition_ids = toset([
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/73c42c96-874c-492b-b04d-ab87d138a893",
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190"
  ])
}

# Reference existing resources
data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = var.ai_foundry_name
  parent_id = data.azurerm_resource_group.rg.id
}

data "azapi_resource" "ai_project" {
  type                   = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name                   = var.ai_project_name
  parent_id              = data.azapi_resource.ai_foundry.id
  response_export_values = ["identity.principalId"]
}

data "azurerm_application_insights" "appi" {
  name                = var.application_insights_name
  resource_group_name = var.resource_group_name
}

# Create the account-level connection
resource "azapi_resource" "account_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = "${var.ai_foundry_name}-appinsights"
  parent_id                 = data.azapi_resource.ai_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AppInsights"
      target        = data.azurerm_application_insights.appi.id
      authType      = "ApiKey"
      isSharedToAll = var.is_shared_to_all
      credentials = {
        key = data.azurerm_application_insights.appi.connection_string
      }
      metadata = {
        ApiType    = "Azure"
        ResourceId = data.azurerm_application_insights.appi.id
      }
    }
  }
}

# Create the project-level connection
resource "azapi_resource" "project_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = var.application_insights_name
  parent_id                 = data.azapi_resource.ai_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AppInsights"
      target        = data.azurerm_application_insights.appi.id
      authType      = "ApiKey"
      isSharedToAll = var.is_shared_to_all
      credentials = {
        key = data.azurerm_application_insights.appi.connection_string
      }
      metadata = {
        ApiType    = "Azure"
        ResourceId = data.azurerm_application_insights.appi.id
      }
    }
  }
}

# Grant the project managed identity read access to the Application Insights component
resource "azurerm_role_assignment" "appi_reader" {
  for_each                         = local.reader_role_definition_ids
  scope                            = data.azurerm_application_insights.appi.id
  role_definition_id               = each.value
  principal_id                     = data.azapi_resource.ai_project.output.identity.principalId
  skip_service_principal_aad_check = true
}

output "account_connection_id" {
  value = azapi_resource.account_connection.id
}

output "project_connection_id" {
  value = azapi_resource.project_connection.id
}
