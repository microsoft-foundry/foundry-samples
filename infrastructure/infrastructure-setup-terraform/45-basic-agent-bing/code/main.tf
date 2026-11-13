########## Create infrastructure resources
##########

## Get subscription data
data "azurerm_client_config" "current" {}

## Create a random string for unique naming
resource "random_string" "unique" {
  length      = 4
  min_numeric = 4
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

locals {
  account_name = lower("${var.ai_services_name}${random_string.unique.result}")
}

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Step 1: Create AI Foundry account and deploy model
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.account_name
  location  = azurerm_resource_group.rg.location
  parent_id = azurerm_resource_group.rg.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.account_name
      disableLocalAuth       = false
      publicNetworkAccess    = "Enabled"
      networkAcls = {
        defaultAction       = "Allow"
        virtualNetworkRules = []
        ipRules             = []
      }
    }
  }
}

resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = var.model_capacity
      name     = var.model_sku_name
    }
    properties = {
      model = {
        name    = var.model_name
        format  = var.model_format
        version = var.model_version
      }
    }
  }
}

## Step 2: Create AI Foundry project
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = var.project_name
  location  = var.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = var.project_description
      displayName = var.project_display_name
    }
  }
}

## Step 3: Create Bing Search resource
resource "azapi_resource" "bing_search" {
  type                      = "Microsoft.Bing/accounts@2020-06-10"
  name                      = "bingsearch-${local.account_name}"
  parent_id                 = azurerm_resource_group.rg.id
  location                  = "global"
  schema_validation_enabled = false

  body = {
    sku = {
      name = "G1"
    }
    kind = "Bing.Grounding"
  }
}

## Get Bing Search keys
data "azapi_resource_action" "bing_keys" {
  type                   = "Microsoft.Bing/accounts@2020-06-10"
  resource_id            = azapi_resource.bing_search.id
  action                 = "listKeys"
  response_export_values = ["key1"]
}

## Step 4: Create Bing Search connection using the Bing resource key
resource "azapi_resource" "bing_connection" {
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview"
  name      = "bing-grounding"
  parent_id = azapi_resource.ai_foundry.id

  body = {
    properties = {
      category      = "ApiKey"
      target        = "https://api.bing.microsoft.com/"
      authType      = "ApiKey"
      isSharedToAll = true
      credentials = {
        key = data.azapi_resource_action.bing_keys.output.key1
      }
      metadata = {
        ApiType    = "Azure"
        Location   = azapi_resource.bing_search.location
        ResourceId = azapi_resource.bing_search.id
      }
    }
  }
}
