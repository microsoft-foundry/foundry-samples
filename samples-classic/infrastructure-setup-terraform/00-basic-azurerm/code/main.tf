## Create a random string
## 
resource "random_string" "unique" {
  length      = 5
  min_numeric = 5
  numeric     = true
  special     = false
  lower       = true
  upper       = false
}

## Create a resource group for the resources to be stored in
##
resource "azurerm_resource_group" "rg" {
  name     = "rg-aifoundry${random_string.unique.result}"
  location = var.location
}

## Create an AI Foundry resource
##

resource "azurerm_cognitive_account" "ai_foundry" {
  name                = "aifoundry${random_string.unique.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  kind                = "AIServices"

  identity {
    type = "SystemAssigned"
  }

  sku_name = "S0"

  # required for stateful development in Foundry including agent service
  custom_subdomain_name = "aifoundry${random_string.unique.result}"
  project_management_enabled = true

  tags = {
    Acceptance = "Test"
  }
}

## Create a deployment for OpenAI's GPT-4o in the AI Foundry resource
##
resource "azurerm_cognitive_deployment" "aifoundry_deployment_gpt_4o" {
  depends_on = [
    azurerm_cognitive_account.ai_foundry
  ]

  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.ai_foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 1
  }

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }
}