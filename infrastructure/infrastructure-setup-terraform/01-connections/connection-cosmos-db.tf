# Example: Azure Cosmos DB Connection
# This example shows how to create a connection from AI Foundry to a new or existing Azure Cosmos DB account.
# It's the Terraform version of infrastructure-setup-bicep/01-connections/connection-cosmos-db.bicep.
# The connection uses Microsoft Entra ID (AAD) authentication, so no key is involved.

terraform {
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
  description = "Resource group containing the AI Foundry account and the Cosmos DB account"
  type        = string
}

variable "cosmos_db_account_name" {
  description = "Name of the Cosmos DB account (default: cosmos-<ai_foundry_name>)"
  type        = string
  default     = null
}

variable "location" {
  description = "Azure region for a new Cosmos DB account"
  type        = string
  default     = "westus"
}

variable "create_new_cosmos_db" {
  description = "Create a new Cosmos DB account or use an existing one"
  type        = bool
  default     = true
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

# Conditionally create a new Cosmos DB account
resource "azapi_resource" "cosmos_db" {
  count     = var.create_new_cosmos_db ? 1 : 0
  type      = "Microsoft.DocumentDB/databaseAccounts@2024-11-15"
  name      = local.cosmos_db_account_name
  parent_id = data.azapi_resource.rg.id
  location  = local.cosmos_db_region

  body = {
    kind = "GlobalDocumentDB"
    properties = {
      consistencyPolicy = {
        defaultConsistencyLevel = "Session"
      }
      disableLocalAuth             = true
      enableAutomaticFailover      = false
      enableMultipleWriteLocations = false
      publicNetworkAccess          = "Enabled"
      enableFreeTier               = false
      locations = [
        {
          locationName     = local.cosmos_db_region
          failoverPriority = 0
          isZoneRedundant  = false
        }
      ]
      databaseAccountOfferType = "Standard"
    }
  }

  response_export_values = ["properties.documentEndpoint", "location"]

  lifecycle {
    # Cosmos DB reports locationName as the region's display name (for example, "West US"),
    # which would otherwise show as a change on every plan.
    ignore_changes = [body.properties.locations]
  }
}

# Reference an existing Cosmos DB account
data "azapi_resource" "existing_cosmos_db" {
  count                  = var.create_new_cosmos_db ? 0 : 1
  type                   = "Microsoft.DocumentDB/databaseAccounts@2024-11-15"
  name                   = local.cosmos_db_account_name
  parent_id              = data.azapi_resource.rg.id
  response_export_values = ["properties.documentEndpoint", "location"]
}

locals {
  cosmos_db_account_name = coalesce(var.cosmos_db_account_name, "cosmos-${var.ai_foundry_name}")
  # Like the Bicep sample, use westus when location is a canary region
  cosmos_db_region   = contains(["eastus2euap", "centraluseuap"], var.location) ? "westus" : var.location
  cosmos_db_id       = var.create_new_cosmos_db ? azapi_resource.cosmos_db[0].id : data.azapi_resource.existing_cosmos_db[0].id
  cosmos_db_endpoint = var.create_new_cosmos_db ? azapi_resource.cosmos_db[0].output.properties.documentEndpoint : data.azapi_resource.existing_cosmos_db[0].output.properties.documentEndpoint
  # The location as Cosmos DB reports it (for example, "West US"), as the Bicep sample sends it
  cosmos_db_location = var.create_new_cosmos_db ? azapi_resource.cosmos_db[0].output.location : data.azapi_resource.existing_cosmos_db[0].output.location
}

# Create Cosmos DB connection
resource "azapi_resource" "cosmos_db_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name                      = "${var.ai_foundry_name}-cosmosdb"
  parent_id                 = data.azapi_resource.ai_foundry.id
  schema_validation_enabled = false # the provider's schema limits names to 33 characters; the service accepts longer ones

  body = {
    properties = {
      category      = "CosmosDb"
      target        = local.cosmos_db_endpoint
      authType      = "AAD" # Cosmos DB only supports AAD authentication when disableLocalAuth is true
      isSharedToAll = var.is_shared_to_all
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.cosmos_db_id
        location   = local.cosmos_db_location
      }
    }
  }

  lifecycle {
    # The service stores isSharedToAll = true on an account-level connection, whatever value is sent
    ignore_changes = [body.properties.isSharedToAll]
  }
}

output "connection_id" {
  value = azapi_resource.cosmos_db_connection.id
}
