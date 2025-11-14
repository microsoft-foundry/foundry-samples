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
resource "azapi_resource" "rg" {
  type      = "Microsoft.Resources/resourceGroups@2021-04-01"
  name      = "rg-aifoundry-${random_string.unique.result}"
  location  = var.location
}

########## Create AI Foundry resource
##########

## Create the AI Foundry resource
##
resource "azapi_resource" "ai_foundry" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = "aifoundry${random_string.unique.result}"
  parent_id                 = azapi_resource.rg.id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }

    properties = {
      # Support both Entra ID and API Key authentication for Cognitive Services account
      disableLocalAuth = false

      # Specifies that this is an AI Foundry resourceyes
      allowProjectManagement = true

      # Set custom subdomain name for DNS names created for this Foundry resource
      customSubDomainName = "aifoundry${random_string.unique.result}"
    }
  }
}

## Create a deployment for OpenAI's GPT-4o in the AI Foundry resource
##
resource "azapi_resource" "aifoundry_deployment_gpt_4o" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name      = "gpt-4o"
  parent_id = azapi_resource.ai_foundry.id
  depends_on = [
    azapi_resource.ai_foundry
  ]

  body = {
    sku = {
      name     = "GlobalStandard"
      capacity = 1
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = "gpt-4o"
        version = "2024-11-20"
      }
    }
  }
}

## Create AI Foundry project
##
resource "azapi_resource" "ai_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = "project${random_string.unique.result}"
  parent_id                 = azapi_resource.ai_foundry.id
  location                  = var.location
  schema_validation_enabled = false

  body = {
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }

    properties = {
      displayName = "project"
      description = "My first project"
    }
  }
}
