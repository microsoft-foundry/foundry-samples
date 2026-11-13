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

## Create a resource group
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Create AI Foundry account with custom subdomain
resource "azapi_resource" "ai_foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = var.custom_subdomain_name
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
      customSubDomainName    = var.custom_subdomain_name
      disableLocalAuth       = false
      publicNetworkAccess    = "Enabled"
    }
  }
}

## Create AI Foundry project
resource "azapi_resource" "ai_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = var.ai_project_name
  location  = var.location
  parent_id = azapi_resource.ai_foundry.id

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }
}

## Deploy model
resource "azapi_resource" "model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.model_name
  parent_id = azapi_resource.ai_foundry.id

  body = {
    sku = {
      capacity = 1
      name     = "GlobalStandard"
    }
    properties = {
      model = {
        name    = var.model_name
        format  = "OpenAI"
        version = var.model_version
      }
    }
  }
}
